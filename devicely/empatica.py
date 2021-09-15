"""
Empatica E4 is a wearable device that offers real-time physiological data
acquisition such as blood volume pulse, electrodermal activity (EDA), heart
rate, interbeat intervals, 3-axis acceleration and skin temperature.
"""

import os
import random

import numpy as np
import pandas as pd


class EmpaticaReader:
    """
    Read, timeshift and write data generated by Empatica E4.

    Attributes
    ----------
    start_times : dict
        Contain the timestamp of the first measurement for all
        measured signals (BVP, ACC, etc.).

    sample_freqs : dict ]
        Contain the sampling frequencies of all measured signals
        in Hz.

    IBI : pandas.DataFrame
        Contain inter-beat interval data. The column
        "seconds_since_start" is the time in seconds between the start of
        measurements and the column "IBI" is the duration in seconds between
        consecutive beats.

    ACC : pandas.DataFrame
        Contain the data measured with the onboard MEMS type
        3-axis accelerometer, indexed by time of measurement.

    BVP : pandas.DataFrame
        Contain blood volume pulse data, indexed by time of
        measurement.

    EDA : pandas.DataFrame
        Contain data captured from the electrodermal activity
        sensor, indexed by time of measurement.

    HR : pandas.DataFrame
        Contain heart rate data, indexed by time of
        measurement.

    TEMP : pandas.DataFrame
        Contain temperature data, indexed by time of
        measurement.

    data : pandas.DataFrame
        Joined dataframe of the ACC, BVP, EDA, HR and TEMP
        dataframes (see above). May contain NaN values because sampling
        frequencies differ across signals.
    """

    def __init__(self, path):
        """
        Parse the csv files located in the specified directory into dataframes.

        Parameters
        ----------
        path : str
            Path of the directory that contains the individual signal csv
            files. The files must be named ACC.csv, BVP.csv, EDA.csv, HR.csv,
            IBI.csv and TEMP.csv. If present, the file tags.csv is also read.
        """

        self.start_times = {}
        self.sample_freqs = {}

        files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]

        if files is None:
            print('Empty directory. Nothing to read.')
            return None

        self.ACC = self._read_signal(os.path.join(path, 'ACC.csv'), 'ACC', col_names=['X', 'Y', 'Z'])
        self.BVP = self._read_signal(os.path.join(path, 'BVP.csv'), 'BVP')
        self.EDA = self._read_signal(os.path.join(path, 'EDA.csv'), 'EDA')
        self.HR = self._read_signal(os.path.join(path, 'HR.csv'), 'HR')
        self.TEMP = self._read_signal(os.path.join(path, 'TEMP.csv'), 'TEMP')
        self.IBI = self._read_ibi(os.path.join(path, 'IBI.csv'))

        self.tags = self._read_tags(os.path.join(path, 'tags.csv'))

        self.data = self._get_joined_dataframe()

    def write(self, dir_path):
        """
        Write the signal dataframes back to individual csv files formatted the
        same way as they were read.

        Parameters
        ----------
        path : str
            Path of the directory in which the csv files are created.

            If the directory exists, the csv files are written using writing mode 'w'
            ignoring other files in the directory.

            If the directory doe not exist, it will be created.
        """

        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        if self.ACC is not None:
            self._write_signal(os.path.join(dir_path, 'ACC.csv'), self.ACC, 'ACC')
        if self.BVP is not None:
            self._write_signal(os.path.join(dir_path, 'BVP.csv'), self.BVP, 'BVP')
        if self.EDA is not None:
            self._write_signal(os.path.join(dir_path, 'EDA.csv'), self.EDA, 'EDA')
        if self.HR is not None:
            self._write_signal(os.path.join(dir_path, 'HR.csv'), self.HR, 'HR')
        if self.TEMP is not None:
            self._write_signal(os.path.join(dir_path, 'TEMP.csv'), self.TEMP, 'TEMP')
        if self.IBI is not None:
            self._write_ibi(os.path.join(dir_path, 'IBI.csv'))
        if self.tags is not None:
            self._write_tags(os.path.join(dir_path, 'tags.csv'))

    def _read_signal(self, path, signal_name, col_names=None):
        try:
            if os.stat(path).st_size > 0:
                with open(path, 'r') as file:
                    start_time_str = file.readline().split(', ')[0]
                    self.start_times[signal_name] = pd.Timestamp(float(start_time_str), unit='s')
                    sample_freq_str = file.readline().split(', ')[0]
                    self.sample_freqs[signal_name] = float(sample_freq_str)
                    col_names = [signal_name] if col_names is None else col_names
                    dataframe = pd.read_csv(file, header=None, names=col_names)
                    dataframe.index = pd.date_range(
                        start=self.start_times[signal_name],
                        freq=f"{1 / self.sample_freqs[signal_name]}S",
                        periods=len(dataframe))
                    if col_names is not None:
                        dataframe.rename(dict(enumerate(col_names)), inplace=True)
                    else:
                        dataframe.rename({0: signal_name}, inplace=True)

                    return dataframe.squeeze()
            else:
                print(f"Not reading signal because the file {path} is empty.")
        except OSError:
            print(f"Not reading signal because the file {path} does not exist.")

        return None

    def _write_signal(self, path, dataframe, signal_name):
        n_cols = len(dataframe.columns) if isinstance(dataframe, pd.DataFrame) else 1
        meta = np.array([[self.start_times[signal_name].value / 1e9] * n_cols,
                            [self.sample_freqs[signal_name]] * n_cols])
        with open(path, 'w') as file:
            np.savetxt(file, meta, fmt='%s', delimiter=', ', newline='\n')
            dataframe.to_csv(file, index=None, header=None, line_terminator='\n')

    def _read_ibi(self, path):
        try:
            if os.stat(path).st_size > 0:
                with open(path, 'r') as file:
                    start_time = pd.Timestamp(float(file.readline().split(',')[0]), unit='s')
                    self.start_times['IBI'] = start_time
                    df = pd.read_csv(file, names=['time', 'IBI'], header=None)
                    df['time'] = pd.to_timedelta(df['time'], unit='s')
                    df['time'] = start_time + df['time']
                    return df.set_index('time') 
            else:
                print(f"Not reading signal because the file {path} is empty.")
        except OSError:
            print(f"Not reading signal because the file {path} does not exist.")

        return None

    def _write_ibi(self, path):
        with open(path, 'w') as file:
            file.write(f"{self.start_times['IBI'].value // 1e9}, IBI\n")
            write_df = self.IBI.copy()
            write_df.index = (write_df.index - self.start_times['IBI']).values.astype(int) / 1e9
            write_df.to_csv(file, header=None, line_terminator='\n')

    def _read_tags(self, path):
        try:
            if os.stat(path).st_size > 0:
                return pd.read_csv(path, header=None,
                                         parse_dates=[0],
                                         date_parser=lambda x : pd.to_datetime(x, unit='s'),
                                         names=['tags'],
                                         squeeze=True)

            else:
                print(f"Not reading tags because the file {path} is empty.")
        except OSError:
            print(f"Not reading tags because the file {path} does not exist.")

        return None

    def _write_tags(self, path):
        if self.tags is not None:
            tags_write_series = self.tags.map(lambda x: x.value / 1e9)
            tags_write_series.to_csv(path, header=None, index=None, line_terminator='\n')

    def timeshift(self, shift='random'):
        """
        Timeshift all time related columns as well as the starting_times dict.

        Parameters
        ----------
        shift : None/'random', pd.Timestamp or pd.Timedelta
            If shift is not specified, shifts the data by a random time interval
            between one month and two years to the past.

            If shift is a timdelta, adds that timedelta to all time-related attributes.

            If shift is a timestamp, shifts the data such that the earliest entry
            has that timestamp. The remaining values will mantain the same
            time difference to the first entry.
        """

        if shift == 'random':
            one_month = pd.Timedelta('- 30 days').value
            two_years = pd.Timedelta('- 730 days').value
            random_timedelta = pd.Timedelta(random.uniform(one_month, two_years))
            self.timeshift(random_timedelta)

        dataframes = []
        variables = [self.ACC, self.BVP, self.EDA,
                     self.HR, self.TEMP, self.data]
        for variable in variables:
            if variable is not None:
                dataframes.append(variable)

        if isinstance(shift, pd.Timestamp):
            min_start_time = min(self.start_times.values())
            new_start_times = dict()
            for signal_name, start_time in self.start_times.items():
                new_start_times[signal_name] = shift + (start_time - min_start_time)
            self.start_times = new_start_times
            if self.tags is not None:
                timedeltas = self.tags - self.tags.min()
                self.tags = shift + timedeltas
            for dataframe in dataframes:
                timedeltas = dataframe.index - dataframe.index.min()
                dataframe.index = shift + timedeltas

        if isinstance(shift, pd.Timedelta):
            for signal_name in self.start_times:
                self.start_times[signal_name] += shift
            if self.tags is not None:
                self.tags += shift
            for dataframe in dataframes:
                dataframe.index += shift

    def _get_joined_dataframe(self):
        dataframes = []
        variables = [self.ACC, self.BVP, self.EDA,
                     self.HR, self.TEMP]
        for variable in variables:
            if variable is not None:
                dataframes.append(variable)

        if not dataframes:
            print('No joined dataframe possible due to lack of data.')
            return None

        joined_idx = pd.concat([pd.Series(dataframe.index) for dataframe in dataframes])
        joined_idx = pd.Index(joined_idx.drop_duplicates().sort_values())

        joined_dataframe = pd.DataFrame(index=joined_idx)
        if self.ACC is not None:
            joined_dataframe.loc[self.ACC.index, 'ACC_X'] = self.ACC['X']
            joined_dataframe.loc[self.ACC.index, 'ACC_Y'] = self.ACC['Y']
            joined_dataframe.loc[self.ACC.index, 'ACC_Z'] = self.ACC['Z']
        if self.BVP is not None:
            joined_dataframe.loc[self.BVP.index, 'BVP'] = self.BVP
        if self.EDA is not None:
            joined_dataframe.loc[self.EDA.index, 'EDA'] = self.EDA
        if self.HR is not None:
            joined_dataframe.loc[self.HR.index, 'HR'] = self.HR
        if self.TEMP is not None:
            joined_dataframe.loc[self.TEMP.index, 'TEMP'] = self.TEMP

        return joined_dataframe
