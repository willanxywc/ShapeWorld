from models.TFMacros.tf_macros import *


def model(model, inputs, **parameters):
    agreement = (
        (
            Input(name='caption', shape=parameters['caption_shape'], dtype='int', tensor=inputs.get('caption')) >>
            Embedding(indices=parameters['vocabulary_size'], size=32),
            Input(name='caption_length', shape=(), dtype='int', tensor=inputs.get('caption_length'))
        ) >>
        Rnn(size=64, unit=Lstm) >>
        Select(index=0) >>
        Reduction(reduction=parameters.get('caption_reduction', 'mean'), axis=1) >>
        Dense(size=512) >>
        Binary(name='agreement', soft=parameters.get('soft', 0.0), tensor=inputs.get('agreement'))
    )
    return agreement
