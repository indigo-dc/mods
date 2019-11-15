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
Created on Mon Nov 07 07:44:07 2019

Train models with first order differential to monitor changes

@author: stefan dlugolinsky
@author: giang nguyen
"""

import os

import pkg_resources
from dataclasses import dataclass
from keras import backend
from marshmallow import Schema, fields, INCLUDE

import mods.config as cfg
import mods.dataset.data_utils as dutils
import mods.dataset.make_dataset as mdata
import mods.models.mods_model as MODS
import mods.utils as utl
from mods.mods_types import TimeRange


class TimeRangeField(fields.Field):
    def _serialize(self, value: TimeRange, attr, obj, **kwargs):
        return str(value)

    def _deserialize(self, value: str, attr, data, **kwargs):
        return TimeRange.from_str(value)


@dataclass
class TrainArgs:
    model_name: str
    data_select_query: str
    train_time_range: TimeRange
    train_time_ranges_excluded: list
    test_time_range: TimeRange
    test_time_ranges_excluded: list
    window_slide: str
    sequence_len: int
    model_delta: bool
    model_type: str
    num_epochs: int
    epochs_patience: int
    blocks: int
    steps_ahead: int
    batch_size: int


class TrainArgsSchema(Schema):
    class Meta:
        unknown = INCLUDE

    model_name = fields.Str(
        required=False,
        missing=cfg.model_name,
        description="Name of the model"
    )
    data_select_query = fields.Str(
        required=False,
        missing=cfg.train_data_select_query,
        description= \
            """
            format: p1;p2|c1|c2~renamed|...;...#c5,c6,...
                p1, p2, ... - protocols; e.g., conn, http, ssh
                c1, c2, ... - columns
                #           - columns to merge data over
            """
    )
    train_time_range = TimeRangeField(
        required=False,
        missing=cfg.train_time_range
    )
    train_time_ranges_excluded = fields.List(
        TimeRangeField,
        required=False,
        missing=[cfg.train_time_range, cfg.test_time_range]
    )
    test_time_range = TimeRangeField(
        required=False,
        missing=cfg.test_time_range,
        description= \
            """
            format: ${LBRACKET}YYYY-MM-DD,YYYY-MM-DD${RBRACKET}
                ${LBRACKET}: closed: < or open: (
                ${RBRACKET}: closed: > or open: )
            """
    )
    test_time_ranges_excluded = fields.List(
        TimeRangeField,
        required=False,
        missing=[cfg.train_time_range, cfg.test_time_range]
    )
    window_slide = fields.Str(
        required=False,
        missing=cfg.train_ws,
        enum=cfg.train_ws_choices,
        description="window length and slide duration"
    )
    sequence_len = fields.Integer(
        required=False,
        missing=cfg.sequence_len,
        description="length of the training sequence; e.g., 6, 9, 12"
    )
    model_delta = fields.Boolean(
        required=False,
        missing=cfg.model_delta,
        enum=[True, False],
        description=""
    )
    model_type = fields.Str(
        required=False,
        missing=cfg.model_type,
        enum=cfg.model_types,
        description=""
    )
    num_epochs = fields.Integer(
        required=False,
        missing=cfg.num_epochs,
        description=""
    )
    epochs_patience = fields.Integer(
        required=False,
        missing=cfg.epochs_patience,
        description=""
    )
    blocks = fields.Integer(
        required=False,
        missing=cfg.blocks,
        description=""
    )
    steps_ahead = fields.Integer(
        required=False,
        missing=cfg.steps_ahead,
        description=""
    )
    batch_size = fields.Integer(
        required=False,
        missing=cfg.batch_size,
        description=""
    )


def load_model(
        model_name=cfg.model_name,
        models_dir=cfg.app_models
):
    """
    Function loads existing MODS model

    :param model_name: file name of the model ('zip' extension is optional)
    :param models_dir:
    :return: mods.models.mods_model
    """
    backend.clear_session()
    m = MODS.mods_model(model_name)
    m.load(os.path.join(models_dir, model_name))
    return m


def get_metadata():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_metadata
    :return:
    """
    module = __name__.split('.', 1)

    pkg = pkg_resources.get_distribution(module[0])
    meta = {
        "author": "Author name",
        "description": "Model description",
        "license": "Model's license",
        "url": "https://github.com/deephdc/mods",
        "version": "Model version",
    }

    # override above values by values from PKG-INFO file (loads metadata from setup.cfg)
    for l in pkg.get_metadata_lines("PKG-INFO"):
        llo = l.lower()
        for par in meta:
            if llo.startswith(par.lower() + ":"):
                _, v = l.split(": ", 1)
                meta[par] = v

    return meta


def warm():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.warm
    :return:
    """
    # prepare the data
    if not (os.path.exists(cfg.app_data_features) and os.path.isdir(cfg.app_data_features)):
        mdata.prepare_data()


def get_train_args(**kwargs):
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_train_args
    https://marshmallow.readthedocs.io/en/latest/api_reference.html#module-marshmallow.fields
    :param kwargs:
    :return:
    """
    return TrainArgsSchema().fields


def train(**kwargs):
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.train
    """
    print("train(**kwargs) - kwargs: %s" % (kwargs))

    # use this schema
    schema = TrainArgsSchema()
    # deserialize key-word arguments
    train_args = schema.load(kwargs)

    print('train_args:', train_args)

    model_name = train_args['model_name']

    # support full paths for command line calls
    models_dir = cfg.app_models
    full_paths = train_args['full_paths'] if 'full_paths' in train_args else False
    if full_paths:
        print('full_paths:', full_paths)
        models_dir = os.path.dirname(model_name)
        model_name = os.path.basename(model_name)

    train_time_range_excluded = utl.parse_datetime_ranges(train_args['train_time_ranges_excluded'])
    test_time_range_excluded = utl.parse_datetime_ranges(train_args['test_time_ranges_excluded'])

    # read train data from the datapool
    df_train, cached_file_train = utl.datapool_read(
        train_args['data_select_query'],
        train_args['train_time_range'],
        train_args['window_slide'],
        train_time_range_excluded,
        cfg.app_data_features
    )
    # repair the data
    df_train = utl.fix_missing_num_values(df_train)

    # read test data from the datapool
    df_test, cached_file_test = utl.datapool_read(
        train_args['data_select_query'],
        train_args['train_time_range'],
        train_args['window_slide'],
        test_time_range_excluded,
        cfg.app_data_features
    )
    # repair the data
    df_test = utl.fix_missing_num_values(df_test)

    backend.clear_session()
    model = MODS.mods_model(model_name)
    model.train(
        df_train=df_train,
        sequence_len=train_args['sequence_len'],
        model_delta=train_args['model_delta'],
        model_type=train_args['model_type'],
        num_epochs=train_args['num_epochs'],
        epochs_patience=train_args['epochs_patience'],
        blocks=train_args['blocks'],
        steps_ahead=train_args['steps_ahead'],
        batch_size=train_args['batch_size']
    )

    # evaluate the model
    predictions = model.predict(df_test)
    metrics = utl.compute_metrics(
        df_test[model.get_sequence_len():-train_args['steps_ahead']],
        predictions[:-train_args['steps_ahead']],  # here, we predict # steps_ahead
        model,
    )

    # put computed metrics into the model to be saved in model's zip
    model.update_metrics(metrics)

    # save model locally
    file = model.save(os.path.join(models_dir, model_name))
    dir_remote = cfg.app_models_remote

    # upload model using rclone
    if cfg.app_models_remote:
        out, err = dutils.rclone_call(
            src_path=file,
            dest_dir=dir_remote,
            cmd='copy'
        )
        print('rclone_copy(%s, %s):\nout: %s\nerr: %s' % (file, dir_remote, out, err))

    message = {
        'status': 'ok',
        'dir_models': models_dir,
        'model_name': model_name,
        'steps_ahead': model.get_steps_ahead(),
        'batch_size': model.get_batch_size(),
        'window_slide': train_args['window_slide'],
        'data_select_query': train_args['data_select_query'],
        'train_time_range': str(train_args['train_time_range']),
        'train_time_range_excluded': str(train_args['train_time_range_excluded']),
        'train_cached_df': cached_file_train,
        'test_time_range': str(train_args['test_time_range']),
        'test_time_range_excluded': str(train_args['test_time_range_excluded']),
        'test_cached_df': cached_file_test,
        'evaluation': model.get_metrics(),
    }

    return message


def get_predict_args():
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.get_predict_args
    :return:
    """
    return {
        "model_name": fields.Str(
            required=False,  # force the user to define the value
            missing=cfg.model_name,  # default value to use
            description="Name of the model to train"  # help string
        ),
        "data": fields.Field(
            description="Data file to perform inference on.",
            required=True,
            type="file",
            location="form"
        )
    }


def predict(**kwargs):
    """
    https://docs.deep-hybrid-datacloud.eu/projects/deepaas/en/wip-api_v2/user/v2-api.html#deepaas.model.v2.base.BaseModel.predict
    :param kwargs:
    :return:
    """
    print('predict_file - kwargs: %s' % kwargs)

    # data_prepared = False
    #
    # message = 'Error reading input data'
    #
    # if args:
    #     for arg in args:
    #         message = {'status': 'ok', 'predictions': []}
    #
    #         # prepare data
    #         if not data_prepared:
    #             bootstrap_data = yaml.safe_load(arg.bootstrap_data)
    #             if bootstrap_data or not (
    #                     os.path.exists(cfg.app_data_features) and os.path.isdir(cfg.app_data_features)):
    #                 mdata.prepare_data()
    #                 data_prepared = True
    #
    #         model_name = yaml.safe_load(arg.model_name)
    #         data_file = yaml.safe_load(arg.file)
    #
    #         sep = cfg.pd_sep
    #         skiprows = cfg.pd_skiprows
    #         skipfooter = cfg.pd_skipfooter
    #         header = cfg.pd_header
    #
    #         # support full paths for command line calls
    #         models_dir = cfg.app_models
    #         full_paths = kwargs['full_paths'] if 'full_paths' in kwargs else False
    #
    #         if full_paths:
    #             if model_name == cfg.model_name:
    #                 models_dir = cfg.app_models
    #             else:
    #                 models_dir = os.path.dirname(model_name)
    #                 model_name = os.path.basename(model_name)
    #             if data_file == cfg.data_predict:
    #                 data_file = os.path.join(cfg.app_data_predict, data_file)
    #         else:
    #             data_file = os.path.join(cfg.app_data_predict, data_file)
    #
    #         m = load_model(
    #             models_dir=models_dir,
    #             model_name=model_name
    #         )
    #
    #         # override batch_size
    #         batch_size = yaml.safe_load(arg.batch_size)
    #         m.set_batch_size(batch_size)
    #
    #         df_data = m.read_file_or_buffer(
    #             data_file,
    #             sep=sep,
    #             skiprows=skiprows,
    #             skipfooter=skipfooter,
    #             engine='python',
    #             header=header,
    #             fill_missing_rows_in_timeseries=cfg.fill_missing_rows_in_timeseries
    #         )
    #
    #         df_data = utl.fix_missing_num_values(df_data)
    #
    #         predictions = m.predict(df_data)
    #
    #         message = {
    #             'status': 'ok',
    #             'dir_models': models_dir,
    #             'model_name': model_name,
    #             'data': data_file,
    #             'steps_ahead': m.get_steps_ahead(),
    #             'batch_size': m.get_batch_size(),
    #             'evaluation': utl.compute_metrics(
    #                 df_data[m.get_sequence_len():-m.get_steps_ahead()],
    #                 predictions[:-m.get_steps_ahead()],
    #                 m,
    #             )
    #         }
    #
    #         message['predictions'] = predictions.tolist()
    #
    # return message

# def get_train_args():
#     train_args = cfg.set_train_args()
#
#     # convert default values and possible 'choices' into strings
#     for key, val in train_args.items():
#         val['default'] = str(val['default'])  # yaml.safe_dump(val['default']) #json.dumps(val['default'])
#         if 'choices' in val:
#             val['choices'] = [str(item) for item in val['choices']]
#         print(val['default'], type(val['default']))
#
#     return train_args
#
#
# # !!! deepaas calls get_test_args() to get args for 'predict'
# def get_test_args():
#     predict_args = cfg.set_predict_args()
#
#     # convert default values and possible 'choices' into strings
#     for key, val in predict_args.items():
#         val['default'] = str(val['default'])  # yaml.safe_dump(val['default']) #json.dumps(val['default'])
#         if 'choices' in val:
#             val['choices'] = [str(item) for item in val['choices']]
#         print(val['default'], type(val['default']))
#
#     return predict_args
