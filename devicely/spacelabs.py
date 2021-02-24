"""
Process Spacelabs (SL 90217) data
"""
import csv
import datetime as dt
import random
import xml.etree.ElementTree as ET

import pandas as pd
import xmltodict


from .helpers import recursive_ordered_dict_to_dict

class SpacelabsReader:
    """
    Parses, timeshifts, deidentify and writes data generated by Spacelabs (SL 90217).

    Attributes
    ----------
    data : DataFrame
        DataFrame with the values that were read from the abp file.

    subject : str
        Contains the sujbect's id.
        Can be changed for deidentification.

    valid_measurements : str
        Contains the number of valid measurements in the abp file.

    metadata : dict
        The measurements' metadata. Read from the xml at the bottom of
        the abp file. Can be erased for deidentification.
    """

    def __init__(self, path):
        """
        Reads the abp file generated by the Spacelabs device and saves the parsed DataFrame.

        Parameters
        ----------
        path : str
            Path of the abp file.
        """

        # Metadata Definition
        metadata = pd.read_csv(path, nrows=5, header=None)
        self.subject = str(metadata.loc[0, 0])
        base_date = dt.datetime.strptime(metadata.loc[2, 0], '%d.%m.%Y').date()
        if metadata.loc[4, 0] != 'Unknown Line':
            self.valid_measurements = str(metadata.loc[4, 0])
        else:
            metadata = pd.read_csv(path, nrows=6, header=None)
            self.valid_measurements = str(metadata.loc[5, 0])

        column_names = ['hour', 'minutes', 'SYS(mmHg)', 'DIA(mmHg)', 'x', 'y', 'error', 'z']
        self.data = pd.read_csv(path, sep=',', skiprows=51, skipfooter=1, header=None,
                                names=column_names,
                                parse_dates={'time': ['hour', 'minutes']},
                                date_parser=lambda hours, minutes: dt.time(hour=int(hours), minute=int(minutes)),
                                engine='python')

        # Adjusting Date
        dates = [base_date]
        current_date = base_date
        for i in range(1, len(self.data)):
            previous_row = self.data.iloc[i - 1]
            current_row = self.data.iloc[i]
            if previous_row.time > current_row.time:
                current_date += dt.timedelta(days=1)
            dates.append(current_date)

        self.data.reset_index(inplace=True)
        self.data['timestamp'] = [dt.datetime.combine(dates[i], self.data.time[i]) for i in range(len(dates))]
        self.data['date'] = dates

        order = ['timestamp', 'date', 'time', 'SYS(mmHg)', 'DIA(mmHg)', 'x', 'y', 'z', 'error']
        self.data = self.data[order]

        xml_line = open(path, 'r').readlines()[-1]
        xml_root = ET.fromstring(xml_line)
        self.metadata = {
            'PATIENTINFO' : {'DOB' : xml_root.find('PATIENTINFO').find('DOB').text,
                             'RACE' : xml_root.find('PATIENTINFO').find('RACE').text},
            'REPORTINFO' : {'PHYSICIAN' : xml_root.find('REPORTINFO').find('PHYSICIAN').text,
                            'NURSETECH' : xml_root.find('REPORTINFO').find('NURSETECH').text,
                            'STATUS' : xml_root.find('REPORTINFO').find('STATUS').text,
                            'CALIPERSUMMARY' : {'COUNT' : int(xml_root.find('REPORTINFO').find('CALIPERSUMMARY').find('COUNT').text)}}
        }

    def deidentify(self, subject_id=None):
        """
        Deidentifies the data by removing the original XML metadata and subject id.

        Parameters
        ----------
        subject_id : str, optional
            New subject_id to be written in the deidentified file, by default None.
        """
        # Changing Subject Id
        if subject_id:
            self.subject = subject_id
        else:
            self.subject = 'xxxxxx'

        # Removing XML Metadata
        for key in self.metadata:
            self.metadata[key] = None

    def write(self, path):
        """
        Writes the DataFrame, subject id, valid measurements and metadata
        to the writing path in the same format as it was read.

        Parameters
        ----------
        path : str
            Path to writing csv. Writing mode: 'w'.
        """

        with open(path, 'w') as f:
            f.write(f"\n{self.subject}")
            f.write(8 * '\n')
            f.write("0")
            f.write(8 * '\n')
            f.write(self.data.date[0].strftime("%d.%m.%Y"))
            f.write(7 * '\n')
            f.write("Unknown Line")
            f.write(26 * '\n')
            f.write(self.valid_measurements + "\n")
            printing_df = self.data.drop(columns=['date', 'time'])
            printing_df['hours'] = self.data.time.map(lambda x: x.strftime("%H"))
            printing_df['minutes'] = self.data.time.map(lambda x: x.strftime("%M"))
            order = ['hours', 'minutes', 'SYS(mmHg)', 'DIA(mmHg)', 'x', 'y', 'error', 'z']
            printing_df = printing_df[order]
            printing_df.fillna(-9999, inplace=True)
            printing_df.replace('EB', -9998, inplace=True)
            printing_df.replace('AB', -9997, inplace=True)
            printing_df[['SYS(mmHg)', 'DIA(mmHg)', 'x', 'y', 'error', 'z']] = printing_df[
                ['SYS(mmHg)', 'DIA(mmHg)', 'x', 'y', 'error', 'z']].astype(int).astype(str)
            printing_df.replace('-9999', '""', inplace=True)
            printing_df.replace('-9998', '"EB"', inplace=True)
            printing_df.replace('-9997', '"AB"', inplace=True)
            printing_df.to_csv(f, header=None, index=None, quoting=csv.QUOTE_NONE)
            f.write(xmltodict.unparse({'XML': self.metadata}).split('\n')[1])

            xml_root = ET.Element('XML')
            patient_info = ET.SubElement(xml_root, 'PATIENTINFO')
            report_info = ET.SubElement(xml_root, 'REPORTINFO')

    def timeshift(self, shift='random'):
        """
        Timeshifts the data by shifting all time related columns.

        Parameters
        ----------
        shift : None/'random', pd.Timestamp or pd.Timedelta
            If shift is not specified, shifts the data by a random time interval
            between one month and two years to the past.

            If shift is a timdelta, shifts the data by that timedelta.

            If shift is a timestamp, shifts the data such that the earliest entry
            is at that timestamp and the remaining values keep the same time distance to the first entry.
        """

        eb_dropped = self.data.index.name == 'timestamp'

        if shift == 'random':
            one_month = pd.Timedelta('30 days').value
            two_years = pd.Timedelta('730 days').value
            random_timedelta = - pd.Timedelta(random.uniform(one_month, two_years)).round('min')
            self.timeshift(random_timedelta)
        if isinstance(shift, pd.Timestamp):
            if eb_dropped:
                timedeltas = self.data.index - self.data.index[0]
                self.data.index = shift.round('min') + timedeltas
            else:
                timedeltas = self.data.timestamp - self.data.timestamp[0]
                self.data.timestamp = shift.round('min') + timedeltas
        if isinstance(shift, pd.Timedelta):
            if eb_dropped:
                self.data.index += shift.round('min')
            else:
                self.data.timestamp += shift.round('min')
        if eb_dropped:
            self.data.date = self.data.index.map(lambda timestamp: timestamp.date())
            self.data.time = self.data.index.map(lambda timestamp: timestamp.time())
        else:
            self.data.date = self.data.timestamp.map(lambda timestamp: timestamp.date())
            self.data.time = self.data.timestamp.map(lambda timestamp: timestamp.time())

    def drop_EB(self):
        """
        Drops all entries with "EB"-errors from the DataFrame

        Note
        ----------
        Before dropping, the dataframe has a range index because the timestamps might not be unique.
        After dropping, the timestamp column will be unique and is thus used as an index for easy indexing.
        """

        self.data = self.data[self.data.error != 'EB']
        self.data.set_index('timestamp', inplace=True)

    def set_window(self, window_duration, window_type):
        """
        Set a window around, before or after the blood pressure measurement by creating
        two new columns with the window_start and window_end times.

        Parameters
        ----------
        window_size : pd.Timedelta, datetime.timedelta
            Duration of the window.
        window_type : bffill, bfill, ffill
            Bffill stands for backward-forward fill. The window is defined as half after and half before the start of the measurement.
            Bfill stands for backward fill. The window is defined before the start of the measurement.
            Ffill stands for forward fill. The window is defined after the start of the measurement.
        """
        if (window_type == 'bffill'):
            self.data['window_start'] = self.data.index - window_duration // 2
            self.data['window_end'] = self.data.index + window_duration // 2
        elif (window_type == 'bfill'):
            self.data['window_start'] = self.data.index - window_duration
            self.data['window_end'] = self.data.index
        elif (window_type == 'ffill'):
            self.data['window_start'] = self.data.index
            self.data['window_end'] = self.data.index + window_duration

