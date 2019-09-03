# -*- coding: utf-8 -*-
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Created on Mon Jan 11 13:34:37 2019

@author: giang nguyen
@author: stefan dlugolinsky
"""

DEBUG = False

import io
import json
import os
import tempfile
import time
from zipfile import ZipFile

import keras
import numpy as np
import pandas as pd
from keras import backend as K
from keras.callbacks import EarlyStopping
from keras.callbacks import ModelCheckpoint
from keras.layers import BatchNormalization
from keras.layers import Bidirectional
from keras.layers import CuDNNGRU
from keras.layers import CuDNNLSTM
from keras.layers import Dense
from keras.layers import Dropout
from keras.layers import Flatten
from keras.layers import Input
from keras.layers import RepeatVector
from keras.layers.convolutional import Conv1D
from keras.layers.convolutional import MaxPooling1D
from keras.layers.recurrent import GRU
from keras.layers.recurrent import LSTM
from keras.models import Model
from keras.optimizers import Adam
from keras.preprocessing.sequence import TimeseriesGenerator
from keras_self_attention import SeqSelfAttention
from sklearn.externals import joblib
from sklearn.preprocessing import MinMaxScaler
from tcn import TCN

import mods.config as cfg
import mods.utils as utl


class mods_model:
    # generic
    __FILE = 'file'
    # model
    __MODEL = 'model'
    __MULTIVARIATE = 'multivariate'
    __SEQUENCE_LEN = 'sequence_len'
    __MODEL_DELTA = 'model_delta'
    __INTERPOLATE = 'interpolate'
    __MODEL_TYPE = 'model_type'
    __EPOCHS = 'epochs'
    __EPOCHS_PATIENCE = 'epochs_patience'
    __BLOCKS = 'blocks'
    __STACKED_BLOCKS = 'stacked_blocks'
    __STEPS_AHEAD = 'steps_ahead'
    __BATCH_SIZE = 'batch_size'
    __BATCH_NORMALIZATION = 'batch_normalization'
    __DROPOUT_RATE = 'dropout_rate'
    __TRAINING_TIME = 'training_time'   # moved to metrics.json
    # scaler
    __SCALER = 'scaler'
    # sample data
    __SAMPLE_DATA = 'sample_data'
    __SEP = 'sep'
    __SKIPROWS = 'skiprows'
    __SKIPFOOTER = 'skipfooter'
    __ENGINE = 'engine'
    __USECOLS = 'usecols'

    def __init__(self, name):
        self.name = name
        self.config = None
        self.model = None
        self.__scaler = None
        self.sample_data = None
        self.__metrics = {}
        self.config = self.__default_config()


    # saves the contents of the original file (e.g. file in a zip) into a temp file and runs func over it
    def __func_over_tempfile(self, orig_file, func, mode='wb', *args, **kwargs):
        # create temp file
        _, fname = tempfile.mkstemp()

        with open(fname, mode) as tf:
            # extract model to the temp file
            tf.write(orig_file.read())

            # call the func over the temp file
            result = func(fname, *args, **kwargs)

        # remove the temp file
        os.remove(fname)
        return result


    def __get_sample_data_cfg(self):
        if mods_model.__SAMPLE_DATA in self.config:
            return self.config[mods_model.__SAMPLE_DATA]
        return None


    def save(self, file):
        if not file.lower().endswith('.zip'):
            file += '.zip'
        print('Saving model: %s' % file)

        with ZipFile(file, mode='w') as zip:
            self.__save_config(zip, 'config.json')
            self.__save_model(zip, self.config[mods_model.__MODEL])
            self.__save_scaler(zip, self.config[mods_model.__SCALER])
            self.__save_sample_data(zip, self.__get_sample_data_cfg())
            self.__save_metrics(zip, 'metrics.json')
            zip.close()

        print('Model saved')
        return file


    def load(self, file):
        if not file.lower().endswith('.zip'):
            file += '.zip'
        print('Loading model: %s' % file)

        with ZipFile(file) as zip:
            self.__load_config(zip, 'config.json')
            self.__load_model(zip, self.config[mods_model.__MODEL])
            self.__load_scaler(zip, self.config[mods_model.__SCALER])
            self.__load_sample_data(zip, self.__get_sample_data_cfg())
            self.__load_metrics(zip, 'metrics.json')
            zip.close()

        print('Model loaded')
        self.__init()


    def __save_config(self, zip, file):
        with zip.open(file, mode='w') as f:
            data = json.dumps(self.config)
            f.write(bytes(data, 'utf-8'))


    def __load_config(self, zip, file):
        print('Loading model config')
        with zip.open(file) as f:
            data = f.read()
            self.config = json.loads(data.decode('utf-8'))
        print('Model config:\n%s' % json.dumps(self.config, indent=True))


    def __save_metrics(self, zip, file):
        with zip.open(file, mode='w') as f:
            data = json.dumps(self.__metrics)
            f.write(bytes(data, 'utf-8'))


    def __load_metrics(self, zip, file):
        print('Loading model metrics')
        try:
            with zip.open(file) as f:
                data = f.read()
                self.__metrics = json.loads(data.decode('utf-8'))
            print('Model metrics:\n%s' % json.dumps(self.__metrics, indent=True))
        except Exception as e:
            print('Error: Could not load model metrics [%s]' % str(e))

    def __save_model(self, zip, model_config):
        print('Saving keras model')
        _, fname = tempfile.mkstemp()
        self.model.save(fname)
        zip.write(fname, model_config[mods_model.__FILE])
        os.remove(fname)
        print('Keras model saved')


    def __load_model(self, zip, model_config):
        print('Loading keras model')
        with zip.open(model_config[mods_model.__FILE]) as f:
            self.model = self.__func_over_tempfile(f, keras.models.load_model)
        print('Keras model loaded')


    def __save_scaler(self, zip, scaler_config):
        print('Saving scaler')
        _, fname = tempfile.mkstemp()
        joblib.dump(self.__scaler, fname)
        zip.write(fname, scaler_config[mods_model.__FILE])
        os.remove(fname)
        print('Scaler saved')


    def __load_scaler(self, zip, scaler_config):
        print('Loading scaler')
        with zip.open(scaler_config[mods_model.__FILE]) as f:
            self.__scaler = joblib.load(f)
        print('Scaler loaded')


    def __save_sample_data(self, zip, sample_data_config):
        if sample_data_config is None:
            return

        if self.sample_data is None:
            print('No sample data was set')
            return
        print('Saving sample data')

        with zip.open(sample_data_config[mods_model.__FILE], mode='w') as f:
            self.sample_data.to_csv(
                io.TextIOWrapper(f),
                sep=sample_data_config[mods_model.__SEP],
                skiprows=sample_data_config[mods_model.__SKIPROWS],
                skipfooter=sample_data_config[mods_model.__SKIPFOOTER],
                engine=sample_data_config[mods_model.__ENGINE],
                usecols=lambda col: col in sample_data_config[mods_model.__USECOLS]
            )
        print('Sample data saved:\n%s' % self.sample_data)


    def __load_sample_data(self, zip, sample_data_config):
        if sample_data_config is None:
            return
        print('Loading sample data')

        try:
            with zip.open(sample_data_config[mods_model.__FILE]) as f:
                self.sample_data = pd.read_csv(
                    io.TextIOWrapper(f),
                    sep=sample_data_config[mods_model.__SEP],
                    skiprows=sample_data_config[mods_model.__SKIPROWS],
                    skipfooter=sample_data_config[mods_model.__SKIPFOOTER],
                    engine=sample_data_config[mods_model.__ENGINE],
                    usecols=lambda col: col in sample_data_config[mods_model.__USECOLS]
                )
            print('Sample data loaded:\n%s' % self.sample_data)
        except Exception as e:
            print('Sample data not loaded: %s' % e)


    def load_data(
            self,
            path,
            sep='\t',
            skiprows=0,
            skipfooter=0,
            engine='python',
            usecols=lambda col: [col for col in ['number_of_conn', 'sum_orig_kbytes']],
            header=0
    ):
        print(path)
        df = pd.read_csv(
            open(path),
            sep=sep,
            skiprows=skiprows,
            skipfooter=skipfooter,
            engine=engine,
            usecols=usecols,
            header=header
        )
        return df


    def __default_config(self):
        return {
            mods_model.__MODEL: {
                mods_model.__FILE: 'model.h5',
                mods_model.__SEQUENCE_LEN: cfg.sequence_len,
                mods_model.__MODEL_DELTA: cfg.model_delta,
                mods_model.__INTERPOLATE: cfg.interpolate,
                mods_model.__MODEL_TYPE: cfg.model_type,
                mods_model.__EPOCHS: cfg.num_epochs,
                mods_model.__EPOCHS_PATIENCE: cfg.epochs_patience,
                mods_model.__BLOCKS: cfg.blocks,
                mods_model.__STACKED_BLOCKS: cfg.stacked_blocks,
                mods_model.__STEPS_AHEAD: cfg.steps_ahead,
                mods_model.__BATCH_SIZE: cfg.batch_size,
                mods_model.__BATCH_NORMALIZATION: cfg.batch_normalization,
                mods_model.__DROPOUT_RATE: cfg.dropout_rate,
            },
            mods_model.__SCALER: {
                mods_model.__FILE: 'scaler.pkl'
            }
        }


    def cfg_model(self):
        return self.config[mods_model.__MODEL]

    def set_multivariate(self, multivariate):
        self.cfg_model()[mods_model.__MULTIVARIATE] = multivariate

    def get_multivariate(self):
        return self.cfg_model()[mods_model.__MULTIVARIATE]

    def set_sequence_len(self, sequence_len):
        self.cfg_model()[mods_model.__SEQUENCE_LEN] = sequence_len

    def get_sequence_len(self):
        return self.cfg_model()[mods_model.__SEQUENCE_LEN]

    def set_model_delta(self, model_delta):
        self.cfg_model()[mods_model.__MODEL_DELTA] = model_delta

    def isdelta(self):
        return self.cfg_model()[mods_model.__MODEL_DELTA]

    def set_interpolate(self, interpolate):
        self.cfg_model()[mods_model.__INTERPOLATE] = interpolate

    def get_interpolate(self):
        return self.cfg_model()[mods_model.__INTERPOLATE]

    def set_model_type(self, model_type):
        self.cfg_model()[mods_model.__MODEL_TYPE] = model_type

    def get_model_type(self):
        return self.cfg_model()[mods_model.__MODEL_TYPE]

    def set_epochs(self, epochs):
        self.cfg_model()[mods_model.__EPOCHS] = epochs

    def get_epochs(self):
        return self.cfg_model()[mods_model.__EPOCHS]

    def set_epochs_patience(self, epochs_patience):
        self.cfg_model()[mods_model.__EPOCHS_PATIENCE] = epochs_patience

    def get_epochs_patience(self):
        return self.cfg_model()[mods_model.__EPOCHS_PATIENCE]

    def set_blocks(self, blocks):
        self.cfg_model()[mods_model.__BLOCKS] = blocks

    def get_blocks(self):
        return self.cfg_model()[mods_model.__BLOCKS]

    def set_stacked_blocks(self, stacked_blocks):
        self.cfg_model()[mods_model.__STACKED_BLOCKS] = stacked_blocks

    def get_stacked_blocks(self):
        return self.cfg_model()[mods_model.__STACKED_BLOCKS]

    def set_steps_ahead(self, steps_ahead):
        self.cfg_model()[mods_model.__STEPS_AHEAD] = steps_ahead

    def get_steps_ahead(self):
        return self.cfg_model()[mods_model.__STEPS_AHEAD]

    def set_batch_size(self, batch_size):
        self.cfg_model()[mods_model.__BATCH_SIZE] = batch_size

    def get_batch_size(self):
        return self.cfg_model()[mods_model.__BATCH_SIZE]

    def set_batch_normalization(self, batch_normalization):
        self.cfg_model()[mods_model.__BATCH_NORMALIZATION] = batch_normalization

    def get_batch_normalization(self):
        return self.cfg_model()[mods_model.__BATCH_NORMALIZATION]

    def set_dropout_rate(self, dropout_rate):
        self.cfg_model()[mods_model.__DROPOUT_RATE] = dropout_rate

    def get_dropout_rate(self):
        return self.cfg_model()[mods_model.__DROPOUT_RATE]

    def set_training_time(self, training_time):
        self.__metrics[self.__TRAINING_TIME] = training_time

    def get_training_time(self):
        # backward compatibility
        try:
            t = self.cfg_model()[mods_model.__TRAINING_TIME]
            if t is not None:
                return t
        except Exception as e:
            return self.__metrics[self.__TRAINING_TIME]

    def get_scaler(self):
        if not self.__scaler:
            self.__scaler = MinMaxScaler(feature_range=(0, 1))
        return self.__scaler

    def set_scaler(self, scaler):
        self.__scaler = scaler

    def set_sample_data(self, df):
        self.sample_data = df

    def update_metrics(self, metrics):
        self.__metrics.update(metrics)

    def get_metrics(self):
        return self.__metrics

    def train(
            self,
            df_train,
            sequence_len=cfg.sequence_len,
            model_delta=cfg.model_delta,
            interpolate=cfg.interpolate,
            model_type=cfg.model_type,
            num_epochs=cfg.num_epochs,
            epochs_patience=cfg.epochs_patience,
            blocks=cfg.blocks,
            stacked_blocks=cfg.stacked_blocks,
            steps_ahead=cfg.steps_ahead,
            batch_size=cfg.batch_size,
            batch_normalization=cfg.batch_normalization,
            dropout_rate=cfg.dropout_rate
    ):
        multivariate = len(df_train.columns)
        self.set_multivariate(multivariate)

        if sequence_len is None:
            sequence_len = self.get_sequence_len()
        else:
            self.set_sequence_len(sequence_len)

        if model_delta is None:
            model_delta = self.isdelta()
        else:
            self.set_model_delta(model_delta)

        if interpolate is None:
            interpolate = self.get_interpolate()
        else:
            self.set_interpolate(interpolate)

        if model_type is None:
            model_type = self.get_model_type()
        else:
            self.set_model_type(model_type)

        if num_epochs is None:
            num_epochs = self.get_epochs()
        else:
            self.set_epochs(num_epochs)

        if epochs_patience is None:
            epochs_patience = self.get_epochs_patience()
        else:
            self.set_epochs_patience(epochs_patience)

        if blocks is None:
            blocks = self.get_blocks()
        else:
            self.set_blocks(blocks)

        if stacked_blocks is None:
            stacked_blocks = self.get_stacked_blocks()
        else:
            self.set_stacked_blocks(stacked_blocks)

        if steps_ahead is None:
            steps_ahead = self.get_steps_ahead()
        else:
            self.set_steps_ahead(steps_ahead)

        if batch_size is None:
            batch_size = self.get_batch_size()
        else:
            self.set_batch_size(batch_size)

        if batch_normalization is None:
            batch_normalization = self.get_batch_normalization()
        else:
            self.set_batch_normalization(batch_normalization)

        if dropout_rate is None:
            dropout_rate = self.get_dropout_rate()
        else:
            self.set_dropout_rate(dropout_rate)

        # Define model
        h = None
        x = Input(shape=(sequence_len, multivariate))

        if model_type == 'MLP':  # MLP
            h = Dense(units=multivariate, activation='relu')(x)
            h = Flatten()(h)
        elif model_type == 'autoencoderMLP':  # autoencoder MLP
            nn = [128, 64, 32, 16, 32, 64, 128]
            h = Dense(units=nn[0], activation='relu')(x)
            for n in nn[1:]:
                h = Dense(units=n, activation='relu')(h)
            h = Flatten()(h)
        elif model_type == 'Conv1D':  # CNN
            h = Conv1D(filters=64, kernel_size=2, activation='relu')(x)
            h = MaxPooling1D(pool_size=2)(h)
            h = Flatten()(h)
        elif model_type == 'TCN':  # https://pypi.org/project/keras-tcn/
            h = TCN(return_sequences=False)(x)
        elif model_type == 'stackedTCN' and stacked_blocks > 1:  # stacked TCN
            h = TCN(return_sequences=True)(x)
            if stacked_blocks > 2:
                for i in range(stacked_blocks - 2):
                    h = TCN(return_sequences=True)(h)
            h = TCN(return_sequences=False)(h)
        else:
            if len(K.tensorflow_backend._get_available_gpus()) == 0:  # CPU running
                print('Running on CPU')
                if model_type == 'GRU':  # GRU
                    h = GRU(cfg.blocks)(x)
                elif model_type == 'LSTM':  # LSTM
                    h = LSTM(cfg.blocks)(x)
                elif model_type == 'bidirectLSTM':  # bidirectional LSTM
                    h = Bidirectional(LSTM(cfg.blocks))(x)
                elif model_type == 'attentionLSTM':  # https://pypi.org/project/keras-self-attention/
                    h = Bidirectional(LSTM(cfg.blocks, return_sequences=True))(x)
                    h = SeqSelfAttention(attention_activation='sigmoid')(h)
                    h = Flatten()(h)
                elif model_type == 'seq2seqLSTM':
                    h = LSTM(cfg.blocks)(x)
                    h = RepeatVector(sequence_len)(h)
                    h = LSTM(cfg.blocks)(h)
                elif model_type == 'stackedLSTM' and stacked_blocks > 1:  # stacked LSTM
                    h = LSTM(cfg.blocks, return_sequences=True)(x)
                    if stacked_blocks > 2:
                        for i in range(stacked_blocks - 2):
                            h = LSTM(cfg.blocks, return_sequences=True)(h)
                    h = LSTM(cfg.blocks)(x)
            else:  # GPU running
                print('Running on GPU')
                if model_type == 'GRU':  # GRU
                    h = CuDNNGRU(cfg.blocks)(x)
                elif model_type == 'LSTM':  # LSTM
                    h = CuDNNLSTM(cfg.blocks)(x)
                elif model_type == 'bidirectLSTM':  # bidirectional LSTM
                    h = Bidirectional(CuDNNLSTM(cfg.blocks))(x)
                elif model_type == 'attentionLSTM':  # https://pypi.org/project/keras-self-attention/
                    h = Bidirectional(CuDNNLSTM(cfg.blocks, return_sequences=True))(x)
                    h = SeqSelfAttention(attention_activation='sigmoid')(h)
                    h = Flatten()(h)
                elif model_type == 'seq2seqLSTM':
                    if batch_normalization:  # https://leimao.github.io/blog/Batch-Normalization/
                        h = CuDNNLSTM(cfg.blocks)(x)
                        BatchNormalization()(h)
                        h = RepeatVector(sequence_len)(h)
                        h = CuDNNLSTM(cfg.blocks)(h)
                        BatchNormalization()(h)
                    elif 0.0 < dropout_rate < 1.0:  # dropout
                        h = CuDNNLSTM(cfg.blocks)(x)
                        h = Dropout(dropout_rate)(h)
                        h = RepeatVector(sequence_len)(h)
                        h = CuDNNLSTM(cfg.blocks)(h)
                        h = Dropout(dropout_rate)(h)
                    else:  # seq2seq LSTM
                        h = CuDNNLSTM(cfg.blocks)(x)
                        h = RepeatVector(sequence_len)(h)
                        h = CuDNNLSTM(cfg.blocks)(h)
                elif model_type == 'stackedLSTM' and stacked_blocks > 1:  # stacked LSTM
                    h = CuDNNLSTM(cfg.blocks, return_sequences=True)(x)
                    if stacked_blocks > 2:
                        for i in range(stacked_blocks - 2):
                            h = CuDNNLSTM(cfg.blocks, return_sequences=True)(h)
                    h = CuDNNLSTM(cfg.blocks)(x)

        if h is None:
            raise Exception('model not specified (h is None)')

        y = Dense(units=multivariate, activation='sigmoid')(h)  # 'softmax' for multiclass classification

        self.model = Model(inputs=x, outputs=y)

        # Drawing model
        print(self.model.summary())

        # Optimizer
        opt = Adam(clipnorm=1.0, clipvalue=0.5)

        # Compile model
        self.model.compile(
            loss='mean_squared_error',  # Adam
            optimizer=opt,              # 'adam', 'adagrad', 'rmsprop', opt
            metrics=['mse', 'mae'])     # 'cosine', 'mape'

        # Checkpointing and earlystopping
        filepath = cfg.app_checkpoints + self.name + '-{epoch:02d}.hdf5'
        checkpoints = ModelCheckpoint(
            filepath,
            monitor='loss',
            save_best_only=True,
            mode=max,
            verbose=1
        )

        earlystops = EarlyStopping(
            monitor='loss',
            patience=epochs_patience,
            verbose=1
        )

        callbacks_list = [checkpoints, earlystops]

        # Replace None by 0
        df_train.replace('None', 0, inplace=True)

        # Add missing values
        if self.get_interpolate():
            df_train.interpolate(inplace=True)

        # Data transformation
        # df_train = df_train.values.astype('float32')
        df_train = self.transform(df_train)
        df_train = self.normalize(df_train, self.get_scaler())
        tsg_train = self.get_tsg(df_train, steps_ahead=steps_ahead, batch_size=batch_size)

        if DEBUG:
            print(self.config)

        start_time = time.time()
        self.model.fit_generator(
            tsg_train,
            epochs=num_epochs,
            callbacks=callbacks_list
        )
        self.set_training_time(time.time() - start_time)

    def plot(self, *args):
        print('this method is not yet implemented')

    def __init(self):
        print('Initializing model')
        if self.sample_data is not None:
            self.predict(self.sample_data)
        print('Model initialized')

    # First order differential for numpy array      y' = d(y)/d(t) = f(y,t)
    # be carefull                                   len(dt) == len(data)-1
    # e.g., [5,2,9,1] --> [2-5,9-2,1-9] == [-3,7,-8]
    def delta(self, df):
        if isinstance(df, pd.DataFrame):
            # pandas data frame
            return df.diff(periods=1, axis=0)[1:]
        # numpy ndarray
        return df[1:] - df[:-1]

    def transform(self, df):
        if self.isdelta():
            return self.delta(df)
        else:
            # bucketing, taxo, fuzzy
            return df

    def inverse_transform(self, original, pred_denorm):
        if self.isdelta():
            seql = self.get_sequence_len()
            y = original[seql:]
            utl.dbg_df(y, self.name, 'y.tsv', print=DEBUG, save=DEBUG)
            d = pred_denorm
            utl.dbg_df(d, self.name, 'd.tsv', print=DEBUG, save=DEBUG)
            return y + d
        else:
            return pred_denorm

    # normalizes data, returns np.ndarray
    def normalize(self, df, scaler, fit=True):
        # Scale all metrics but each separately
        df = scaler.fit_transform(df) if fit else scaler.transform(df)
        utl.dbg_scaler(scaler, 'normalize', debug=DEBUG)
        return df

    # inverse method to @normalize
    def inverse_normalize(self, df):
        scaler = self.get_scaler()
        utl.dbg_scaler(scaler, 'inverse_normalize', debug=DEBUG)
        return scaler.inverse_transform(df)


    def get_tsg(self, df,
                steps_ahead=cfg.steps_ahead,
                batch_size=cfg.batch_size
                ):

        x = y = df
        length = self.get_sequence_len()
        if steps_ahead > 1:
            x = df[:-(steps_ahead - 1)]
            y = df[steps_ahead - 1:]

        return TimeseriesGenerator(
            x,
            y,
            length=length,
            sampling_rate=1,
            stride=1,
            batch_size=batch_size
        )


    def predict(self, df):

        utl.dbg_df(df, self.name, 'original', print=DEBUG, save=DEBUG)

        if self.get_interpolate():
            df = df.interpolate()
            utl.dbg_df(df, self.name, 'interpolated', print=DEBUG, save=DEBUG)

        trans = self.transform(df)
        utl.dbg_df(trans, self.name, 'transformed', print=DEBUG, save=DEBUG)

        norm = self.normalize(trans, self.get_scaler(), fit=False)
        utl.dbg_df(norm, self.name, 'normalized', print=DEBUG, save=DEBUG)

        # append #steps_ahead dummy rows at the end of the norm
        # np.ndarray in order to tsg generate last sample
        # for prediction of the future state
        dummy = [np.nan] * self.get_multivariate()
        for i in range(self.get_steps_ahead()):
            norm = np.append(norm, [dummy], axis=0)
        utl.dbg_df(norm, self.name, 'normalized+nan', print=DEBUG, save=DEBUG)

        tsg = self.get_tsg(norm, steps_ahead=self.get_steps_ahead(), batch_size=self.get_batch_size())
        utl.dbg_tsg(tsg, 'norm_tsg', debug=DEBUG)

        pred = self.model.predict_generator(tsg)
        utl.dbg_df(pred, self.name, 'prediction', print=DEBUG, save=DEBUG)

        pred_denorm = self.inverse_normalize(pred)
        utl.dbg_df(pred_denorm, self.name, 'pred_denormalized', print=DEBUG, save=DEBUG)

        pred_invtrans = self.inverse_transform(df, pred_denorm)
        utl.dbg_df(pred_invtrans, self.name, 'pred_inv_trans', print=DEBUG, save=DEBUG)

        if isinstance(pred_invtrans, pd.DataFrame):
            pred_invtrans = pred_invtrans.values

        return pred_invtrans

    # This function wraps pandas._read_csv(), reads the csv data and calls predict() on them
    def read_file_or_buffer(self, *args, **kwargs):
        if kwargs is not None:
            kwargs = {k: v for k, v in kwargs.items() if k in [
                'usecols', 'sep', 'skiprows', 'skipfooter', 'engine', 'header', 'fill_missing_rows'
            ]}

            if 'usecols' in kwargs:
                if isinstance(kwargs['usecols'], str):
                    kwargs['usecols'] = [
                        utl.parse_int_or_str(col)
                        for col in kwargs['usecols'].split(',')
                    ]

            if 'header' in kwargs:
                if isinstance(kwargs['header'], str):
                    kwargs['header'] = [
                        utl.parse_int_or_str(col)
                        for col in kwargs['header'].split(',')
                    ]
                    if len(kwargs['header']) == 1:
                        kwargs['header'] = kwargs['header'][0]
            # print('HEADER: %s' % kwargs['pd_header'])

        df = pd.read_csv(*args, **kwargs)

        if kwargs is not None \
                and 'fill_missing_rows' in kwargs\
                and kwargs['fill_missing_rows'] is True:
            df = utl.fill_missing_rows(df)

        return df

    # not used:
    # def predict_file_or_buffer(self, *args, **kwargs):
    #     df = self.read_file_or_buffer(*args, **kwargs)
    #     return self.predict(df)

    def predict_url(self, url):
        pass

    def eval(self, df):
        interpol = df
        if self.get_interpolate():
            interpol = df.interpolate()
            interpol = interpol.values.astype('float32')
            # print('interpolated:\n%s' % interpol)

        trans = self.transform(interpol)
        # print('transformed:\n%s' % transf)

        norm = self.normalize(trans, self.get_scaler())
        # print('normalized:\n%s' % norm)

        tsg = self.get_tsg(norm, self.get_steps_ahead(), cfg.batch_size_test)

        return self.model.evaluate_generator(tsg)
