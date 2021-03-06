from importlib import import_module
from io import BytesIO
import json
from math import ceil, sqrt
import os
from random import random, randrange
import numpy as np
from PIL import Image
from shapeworld import util
from shapeworld.world import World
from shapeworld.realizers import CaptionRealizer


def dataset(dtype=None, name=None, language=None, config=None):
    # explain type = 'load', 'mixer', possibilities, e.g. with ',', or with ';'?
    assert config is None or isinstance(config, dict) or isinstance(config, str)
    assert dtype is None or isinstance(dtype, str)
    assert name is None or isinstance(name, str)
    load = mix = False
    if config is not None and isinstance(config, str):
        if config[:5] == 'load(' and config[-1] == ')':
            load = True
            config = config[5:-1]
        elif config[:4] == 'mix(' and config[-1] == ')':
            mix = True
            config = config[4:-1]
        assert not load or not mix
        # mix default config when names list
        if mix and not os.path.isfile(config):
            return DatasetMixer(datasets=config.split(','))
        if load and os.path.isdir(config):
            assert dtype and name
            if language is None:
                directory = os.path.join(config, dtype, name)
                config = os.path.join(config, '{}-{}.json'.format(dtype, name))
            else:
                directory = os.path.join(config, '{}-{}'.format(dtype, language), name)
                config = os.path.join(config, '{}-{}-{}.json'.format(dtype, language, name))
        else:
            assert os.path.isfile(config)
            directory = os.path.dirname(config)
        with open(config, 'r') as filehandle:
            config = json.load(fp=filehandle)
        if load and 'directory' not in config:
            config['directory'] = directory
    if load:
        dataset = LoadedDataset(specification=config)
        assert dtype is None or dtype == dataset.type
        assert name is None or name == dataset.name
        assert language is None or language == dataset.language
        return dataset
    if mix:
        dataset = DatasetMixer(**config)
        assert dtype is None or dtype == dataset.type
        return dataset
    if config is not None:
        if 'type' in config:
            if dtype is None:
                dtype = config['type']
            else:
                assert dtype == config['type']
        if 'name' in config:
            if name is None:
                name = config['name']
            else:
                assert name == config['name']
        if 'language' in config:
            if language is None:
                language = config['language']
            else:
                assert language == config['language']
    assert dtype and name
    module = import_module('shapeworld.datasets.{}.{}'.format(dtype, name))
    dclass = module.dataset
    if config is None:
        assert dclass.default_config is not None
        config = dclass.default_config
    else:
        for key, value in dclass.default_config.items():
            if key not in config:
                config[key] = value
    if language is not None:
        config['language'] = language
    dataset = dclass(**config)
    return dataset


def alternatives_type(value_type):
    if len(value_type) > 5 and value_type[:5] == 'alts(' and value_type[-1] == ')':
        return value_type[5:-1], True
    else:
        return value_type, False


def valid_value_type(value_type):
    value_type, alts = alternatives_type(value_type=value_type)
    if alts:
        return value_type in ('int', 'float', 'vector(int)', 'vector(float)', 'text', 'model')
    else:
        return value_type in ('int', 'float', 'vector(int)', 'vector(float)', 'world', 'text', 'model')


class Dataset(object):

    dataset_name = None
    dataset_type = None
    dataset_values = {'world': 'world', 'world_model': 'model'}
    default_config = None

    def __init__(self, world_size, vectors=None, words=None, language=None):
        assert self.__class__.dataset_name
        assert self.__class__.dataset_type
        assert all(valid_value_type(value_type=value_type) for value_type in self.__class__.dataset_values.values())
        assert 'alternatives' not in self.__class__.dataset_values or self.__class__.dataset_values['alternatives'] == 'int'
        assert all(not alternatives_type(value_type=value_type)[1] for value_type in self.__class__.dataset_values.values()) or 'alternatives' in self.__class__.dataset_values
        if isinstance(world_size, int):
            self.world_size = world_size
        else:
            self.world_size = tuple(world_size)
        self.vectors = vectors
        if words is not None and isinstance(words, list):
            assert words is None or words == sorted(words)  # !!!
            words = {words[n]: n + 1 for n in range(len(words))}
            words[''] = 0
            words['[UNKNOWN]'] = len(words)
        self.words = words
        self.language = language

    def __str__(self):
        if self.language is None:
            return '{} {}'.format(self.type, self.name)
        else:
            return '{} {} ({})'.format(self.type, self.name, self.language)

    @property
    def type(self):
        return self.__class__.dataset_type

    @property
    def name(self):
        return self.__class__.dataset_name

    @property
    def values(self):
        return self.__class__.dataset_values

    def specification(self):
        specification = {'type': self.type, 'name': self.name, 'values': self.values}
        if isinstance(self.world_size, int):
            specification['world_size'] = self.world_size
        else:
            specification['world_size'] = list(self.world_size)
        if self.vectors:
            specification['vectors'] = self.vectors
        if self.words:
            specification['words'] = self.words
        if self.language:
            specification['language'] = self.language
        return specification

    @property
    def world_shape(self):
        if isinstance(self.world_size, int):
            return (self.world_size, self.world_size, 3)
        else:
            return (self.world_size[0], self.world_size[1], 3)

    def vector_shape(self, value_name):
        return (self.vectors.get(value_name),)

    @property
    def vocabulary_size(self):
        return len(self.words)

    @property
    def vocabulary(self):
        return list(self.words.keys())

    def zero_batch(self, n, include_model=False, alternatives=False):
        batch = dict()
        for value_name, value_type in self.values.items():
            value_type, alts = alternatives_type(value_type=value_type)
            if alternatives and alts:
                if value_type == 'int':
                    batch[value_name] = [[] for _ in range(n)]
                elif value_type == 'float':
                    batch[value_name] = [[] for _ in range(n)]
                elif value_type == 'vector(int)' or value_type == 'text':
                    batch[value_name] = [[np.zeros(shape=self.vector_shape(value_name), dtype=np.int32)] for _ in range(n)]
                elif value_type == 'vector(float)':
                    batch[value_name] = [[np.zeros(shape=self.vector_shape(value_name), dtype=np.float32)] for _ in range(n)]
                elif value_type == 'model' and include_model:
                    batch[value_name] = [[] for _ in range(n)]
            else:
                if value_type == 'int' and (value_name != 'alternatives' or alternatives):
                    batch[value_name] = np.zeros(shape=(n,), dtype=np.int32)
                elif value_type == 'float':
                    batch[value_name] = np.zeros(shape=(n,), dtype=np.float32)
                elif value_type == 'vector(int)' or value_type == 'text':
                    batch[value_name] = np.zeros(shape=((n,) + self.vector_shape(value_name)), dtype=np.int32)
                elif value_type == 'vector(float)':
                    batch[value_name] = np.zeros(shape=((n,) + self.vector_shape(value_name)), dtype=np.float32)
                elif value_type == 'world':
                    batch[value_name] = np.zeros(shape=((n,) + self.world_shape), dtype=np.float32)
                elif value_type == 'model' and include_model:
                    batch[value_name] = [None] * n
        return batch

    def generate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):  # mode: None, 'train', 'validation', 'test'
        raise NotImplementedError

    def iterate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):
        while True:
            yield self.generate(n=n, mode=mode, noise_range=noise_range, include_model=include_model, alternatives=alternatives)

    def get_html(self, generated, id2word=None):
        return None

    def serialize(self, path, generated, additional=None, filename=None, archive=None, concat_worlds=False, html=False):
        assert not additional or all(value_name not in self.values for value_name in additional)
        if not os.path.isdir(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path))

        id2word = [word for word, _ in sorted(self.words.items(), key=(lambda kv: kv[1]))] if self.words else None

        with util.Archive(path=path, mode='w', archive=archive) as write_file:
            for value_name, value in generated.items():
                Dataset.serialize_value(value=value, value_name=value_name, value_type=self.values[value_name], write_file=write_file, concat_worlds=concat_worlds, id2word=id2word)
            if additional:
                for value_name, (value, value_type) in additional.items():
                    Dataset.serialize_value(value=value, value_name=value_name, value_type=value_type, write_file=write_file, concat_worlds=concat_worlds, id2word=id2word)
            if html:
                html = self.get_html(generated=generated, id2word=id2word)
                assert html is not None
                write_file(filename='data.html', value=html)

    @staticmethod
    def serialize_value(value, value_name, value_type, write_file, concat_worlds=False, id2word=None):
        value_type, alts = alternatives_type(value_type=value_type)
        if value_type == 'int':
            if alts:
                value = '\n'.join(';'.join(str(int(x)) for x in xs) for xs in value) + '\n'
            else:
                value = '\n'.join(str(int(x)) for x in value) + '\n'
            write_file(value_name + '.txt', value)
        elif value_type == 'float':
            if alts:
                value = '\n'.join(';'.join(str(float(x)) for x in xs) for xs in value) + '\n'
            else:
                value = '\n'.join(str(float(x)) for x in value) + '\n'
            write_file(value_name + '.txt', value)
        elif value_type == 'vector(int)' or value_type == 'vector(float)':
            if alts:
                value = '\n'.join(';'.join(','.join(str(x) for x in vector) for vector in vectors) for vectors in value) + '\n'
            else:
                value = '\n'.join(','.join(str(x) for x in vector) for vector in value) + '\n'
            write_file(value_name + '.txt', value)
        elif value_type == 'text':
            assert id2word
            if alts:
                value = '\n\n'.join('\n'.join(' '.join(id2word[word_id] for word_id in text if word_id) for text in texts) for texts in value) + '\n\n'
            else:
                value = '\n'.join(' '.join(id2word[word_id] for word_id in text if word_id) for text in value) + '\n'
            write_file(value_name + '.txt', value)
        elif value_type == 'world':
            if concat_worlds:
                size = ceil(sqrt(len(value)))
                worlds = []
                for y in range(ceil(len(value) / size)):
                    if y < len(value) // size:
                        worlds.append(np.concatenate([value[y * size + x] for x in range(size)], axis=1))
                    else:
                        worlds.append(np.concatenate([value[y * size + x] for x in range(len(value) % size)] + [np.zeros_like(a=value[0]) for _ in range(-len(value) % size)], axis=1))
                worlds = np.concatenate(worlds, axis=0)
                image = World.get_image(world_array=worlds)
                image_bytes = BytesIO()
                image.save(image_bytes, format='bmp')
                write_file(value_name + '.bmp', image_bytes.getvalue(), binary=True)
                image_bytes.close()
            else:
                for n in range(len(value)):
                    image = World.get_image(world_array=value[n])
                    image_bytes = BytesIO()
                    image.save(image_bytes, format='bmp')
                    write_file('{}-{}.bmp'.format(value_name, n), image_bytes.getvalue(), binary=True)
                    image_bytes.close()
        elif value_type == 'model':
            value = json.dumps(value)
            write_file(value_name + '.json', value)

    @staticmethod
    def deserialize_value(value_name, value_type, read_file, num_concat_worlds=0, word2id=None):
        value_type, alts = alternatives_type(value_type=value_type)
        if value_type == 'int':
            value = read_file(value_name + '.txt')
            if alts:
                value = [[int(x) for x in xs.split(';')] for xs in value.split('\n')[:-1]]
            else:
                value = [int(x) for x in value.split('\n')[:-1]]
            return value
        elif value_type == 'float':
            value = read_file(value_name + '.txt')
            if alts:
                value = [[float(x) for x in xs.split(';')] for xs in value.split('\n')[:-1]]
            else:
                value = [float(x) for x in value.split('\n')[:-1]]
            return value
        elif value_type == 'vector(int)':
            value = read_file(value_name + '.txt')
            if alts:
                value = [[[int(x) for x in vector.split(',')] for vector in vectors.split(';')] for vectors in value.split('\n')[:-1]]
            else:
                value = [[int(x) for x in vector.split(',')] for vector in value.split('\n')[:-1]]
            return value
        elif value_type == 'vector(float)':
            value = read_file(value_name + '.txt')
            if alts:
                value = [[[float(x) for x in vector.split(',')] for vector in vectors.split(';')] for vectors in value.split('\n')[:-1]]
            else:
                value = [[float(x) for x in vector.split(',')] for vector in value.split('\n')[:-1]]
            return value
        elif value_type == 'text':
            assert word2id
            value = read_file(value_name + '.txt')
            if alts:
                value = [[[word2id[word] for word in text.split(' ')] for text in texts.split('\n')] for texts in value.split('\n\n')[:-1]]
            else:
                value = [[word2id[word] for word in text.split(' ')] for text in value.split('\n')[:-1]]
            return value
        elif value_type == 'world':
            if num_concat_worlds:
                size = ceil(sqrt(num_concat_worlds))
                image_bytes = read_file(value_name + '.bmp', binary=True)
                assert image_bytes is not None
                image_bytes = BytesIO(image_bytes)
                image = Image.open(image_bytes)
                worlds = World.from_image(image)
                height = worlds.shape[0] // ceil(num_concat_worlds / size)
                assert worlds.shape[0] % ceil(num_concat_worlds / size) == 0
                width = worlds.shape[1] // size
                assert worlds.shape[1] % size == 0
                value = []
                for y in range(ceil(num_concat_worlds / size)):
                    for x in range(size if y < num_concat_worlds // size else num_concat_worlds % size):
                        value.append(worlds[y * height: (y + 1) * height, x * width: (x + 1) * width, :])
            else:
                value = []
                n = 0
                while True:
                    image_bytes = read_file('{}-{}.bmp'.format(value_name, n), binary=True)
                    if image_bytes is None:
                        break
                    image_bytes = BytesIO(image_bytes)
                    image = Image.open(image_bytes)
                    value.append(World.from_image(image))
                    n += 1
            return value
        elif value_type == 'model':
            value = read_file(value_name + '.json')
            value = json.loads(value)
            return value


class LoadedDataset(Dataset):

    dataset_name = 'loaded'
    dataset_type = 'loaded'

    def __init__(self, specification):
        super(LoadedDataset, self).__init__(world_size=specification.pop('world_size'), vectors=specification.pop('vectors', None), words=specification.pop('words', None), language=specification.pop('language', None))
        # assert per_part or not part_once
        self._type = specification.pop('type')
        self._name = specification.pop('name')
        self._values = specification.pop('values')
        self.archive = specification.pop('archive', None)
        self.include_model = specification.pop('include_model', False)
        self.num_concat_worlds = specification.pop('num_concat_worlds', 0)
        self._specification = specification
        self.per_part = True
        self.part_once = False

        self.parts = dict()
        directory = specification['directory']
        for root, dirs, files in os.walk(directory):
            if root == directory:
                assert not files
                assert len(dirs) <= 4 and 'train' in dirs and 'validation' in dirs and 'test' in dirs and (len(dirs) == 3 or 'tf-records' in dirs)
            elif root[len(directory) + 1:] in ('train', 'validation', 'test', 'tf-records'):
                mode = root[len(directory) + 1:]
                if dirs:
                    assert all(d[:4] == 'part' and d[4:].isdigit() for d in dirs)
                    assert not files
                    self.parts[mode] = [os.path.join(root, d) for d in dirs]
                else:
                    assert all(f[:4] == 'part' for f in files)
                    self.parts[mode] = [os.path.join(root, f) for f in files]
        assert self.parts
        self.mode = None
        self.loaded = {value_name: [] for value_name, value_type in self.values.items() if value_type != 'model' or self.include_model}
        self.num_instances = 0

    @property
    def type(self):
        return self._type

    @property
    def name(self):
        return self._name

    @property
    def values(self):
        return self._values

    def specification(self):
        return self._specification

    def __getattr__(self, name):
        if name in self._specification:
            return self._specification[name]
        raise AttributeError

    def get_records_paths(self):
        assert 'tf-records' in self.parts
        return self.parts['tf-records']

    def generate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):
        assert not include_model or self.include_model
        if not self.per_part:
            self.mode = None if mode else 'train'
        while self.mode != mode or self.num_instances < n:
            if self.mode != mode:
                self.mode = mode
                self.loaded = {value_name: [] for value_name, value_type in self.values.items() if value_type not in ('model', 'alts(model)') or self.include_model}
            parts = self.parts[mode]
            part = randrange(len(parts))
            path = parts.pop(part) if self.part_once else parts[part]
            self.num_instances = 0
            with util.Archive(path=path, mode='r', archive=self.archive) as read_file:
                for value_name, value in self.loaded.items():
                    value.extend(Dataset.deserialize_value(value_name=value_name, value_type=self.values[value_name], read_file=read_file, num_concat_worlds=self.num_concat_worlds, word2id=self.words))
                    if self.num_instances:
                        assert len(value) == self.num_instances
                    else:
                        self.num_instances = len(value)

        batch = self.zero_batch(n, include_model=include_model, alternatives=alternatives)
        for i in range(n):
            index = randrange(self.num_instances)
            self.num_instances -= 1
            for value_name, value_type in self.values.items():
                if value_type in ('model', 'alts(model)') and not self.include_model:
                    continue
                value = self.loaded[value_name].pop(index)
                if value_type == 'text':
                    batch[value_name][i][:len(value)] = value
                elif value_type not in ('model', 'alts(model)') or include_model:
                    batch[value_name][i] = value
        if noise_range is not None and noise_range > 0.0:
            for value_name, value_type in self.values.items():
                if value_type == 'world':
                    noise = np.random.normal(loc=0.0, scale=noise_range, size=((n,) + self.world_shape))
                    mask = (noise < -2.0 * noise_range) + (noise > 2.0 * noise_range)
                    while np.any(a=mask):
                        noise -= mask * noise
                        noise += mask * np.random.normal(loc=0.0, scale=noise_range, size=((n,) + self.world_shape))
                        mask = (noise < -2.0 * noise_range) + (noise > 2.0 * noise_range)
                    worlds = batch[value_name]
                    worlds += noise
                    np.clip(worlds, a_min=0.0, a_max=1.0, out=worlds)
        return batch

    def get_html(self, generated, id2word=None):
        module = import_module('shapeworld.datasets.{}.{}'.format(self.type, self.name))
        dclass = module.dataset
        return dclass.get_html(self, generated=generated, id2word=id2word)


class DatasetMixer(Dataset):

    dataset_name = 'mixer'
    dataset_type = 'mixer'

    # accepts Dataset, config, str
    def __init__(self, datasets, consistent_batches=False, distribution=None, train_distribution=None, validation_distribution=None, test_distribution=None):
        assert len(datasets) >= 1
        for n, dataset in enumerate(datasets):
            if not isinstance(dataset, Dataset):
                datasets[n] = Dataset.dataset(config=dataset)
        assert all(dataset.type == datasets[0].type for dataset in datasets)
        assert all(dataset.language == datasets[0].language for dataset in datasets)
        assert all(dataset.values == datasets[0].values for dataset in datasets)
        assert all(dataset.world_size == datasets[0].world_size for dataset in datasets)
        assert all(sorted(dataset.vectors) == sorted(datasets[0].vectors) for dataset in datasets)
        assert all((dataset.words is None) == (datasets[0].words is None) for dataset in datasets)
        # combine vectors and words information
        vectors = {value_name: max(dataset.vectors[value_name] for dataset in datasets) for value_name in datasets[0].vectors}
        words = sorted(set(word for dataset in datasets for word in dataset.words))
        words = {words[n]: n for n in range(len(words))}
        language = datasets[0].language
        super(DatasetMixer, self).__init__(None, vectors=vectors, words=words, language=language)
        for dataset in datasets:
            dataset.vectors = self.vectors
            dataset.words = self.words
        self.datasets = datasets
        self.consistent_batches = consistent_batches
        assert not distribution or len(distribution) == len(datasets)
        distribution = util.value_or_default(distribution, [1] * len(datasets))
        self.distribution = util.cumulative_distribution(distribution)
        assert bool(train_distribution) == bool(validation_distribution) == bool(test_distribution)
        assert not train_distribution or len(train_distribution) == len(validation_distribution) == len(test_distribution) == len(self.distribution)
        self.train_distribution = util.cumulative_distribution(util.value_or_default(train_distribution, distribution))
        self.validation_distribution = util.cumulative_distribution(util.value_or_default(validation_distribution, distribution))
        self.test_distribution = util.cumulative_distribution(util.value_or_default(test_distribution, distribution))

    @property
    def type(self):
        return self.datasets[0].type

    @property
    def name(self):
        return 'mixer'

    @property
    def values(self):
        return self.datasets[0].values

    @property
    def world_size(self):
        return self.datasets[0].world_size

    def generate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):
        if mode is None:
            distribution = self.distribution
        if mode == 'train':
            distribution = self.train_distribution
        elif mode == 'validation':
            distribution = self.validation_distribution
        elif mode == 'test':
            distribution = self.test_distribution
        if self.consistent_batches:
            dataset = util.sample(distribution, self.datasets)
            return dataset.generate(n=n, mode=mode, noise_range=noise_range, include_model=include_model, alternatives=alternatives)
        else:
            batch = self.zero_batch(n, include_model=include_model, alternatives=alternatives)
            for i in range(n):
                dataset = util.sample(distribution, self.datasets)
                generated = dataset.generate(n=1, mode=mode, noise_range=noise_range, include_model=include_model, alternatives=alternatives)
                for value_name, value_type in self.values.items():
                    value = generated[value_name][0]
                    if value_type == 'text':
                        batch[value_name][i][:len(value)] = value
                    else:
                        batch[value_name][i] = value
        return batch


class ClassificationDataset(Dataset):

    dataset_type = 'classification'
    dataset_values = {'world': 'world', 'world_model': 'model', 'classification': 'vector(float)'}

    def __init__(self, world_generator, num_classes, multi_class=False, class_count=False):
        super(ClassificationDataset, self).__init__(world_size=world_generator.world_size, vectors=dict(classification=num_classes))
        assert multi_class or not class_count
        self.world_generator = world_generator
        self.num_classes = num_classes
        self.multi_class = multi_class
        self.class_count = class_count

    def specification(self):
        specification = super(ClassificationDataset, self).specification()
        specification['num_classes'] = self.num_classes
        specification['multi_class'] = self.multi_class
        specification['class_count'] = self.class_count
        return specification

    def get_classes(self, world):  # iterable of classes
        raise NotImplementedError

    def generate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):
        batch = self.zero_batch(n, include_model=include_model, alternatives=alternatives)
        for i in range(n):
            self.world_generator.sample_values(mode=mode)

            while True:
                world = self.world_generator()
                if world is not None:
                    break

            batch['world'][i] = world.get_array(noise_range=noise_range)
            if include_model:
                batch['world_model'][i] = world.model()
            c = None
            for c in self.get_classes(world):
                if self.class_count:
                    batch['classification'][i][c] += 1.0
                else:
                    batch['classification'][i][c] = 1.0
            if not self.multi_class:
                assert c is not None
        return batch

    def get_html(self, generated, id2word=None):
        classifications = generated['classification']
        data_html = list()
        for n, classification in enumerate(classifications):
            data_html.append('<div class="instance"><div class="world"><img src="world-{world}.bmp" alt="world-{world}.bmp"></div><div class="classification"><p>'.format(world=n))
            comma = False
            for c, count in enumerate(classification):
                if count == 0.0:
                    continue
                if comma:
                    data_html.append(',&ensp;')
                else:
                    comma = True
                if self.class_count:
                    data_html.append('{count:.0f} &times; class {c}'.format(c=c, count=count))
                else:
                    data_html.append('class {c}'.format(c=c))
            data_html.append('</p></div></div>')
        html = '<!DOCTYPE html><html><head><title>{dtype} {name}</title><style>.data{{width: 100%; height: 100%;}} .instance{{width: 100%; margin-top: 1px; margin-bottom: 1px; background-color: #CCCCCC;}} .world{{height: {world_height}px; display: inline-block; vertical-align: middle;}} .classification{{display: inline-block; vertical-align: middle; margin-left: 10px;}}</style></head><body><div class="data">{data}</div></body></html>'.format(
            dtype=self.type,
            name=self.name,
            world_height=self.world_shape[0],
            data=''.join(data_html)
        )
        return html


class CaptionAgreementDataset(Dataset):

    MAX_ATTEMPTS = 10
    RESAMPLE_CAPTIONER = 10
    dataset_type = 'agreement'
    dataset_values = {'world': 'world', 'world_model': 'model', 'caption': 'text', 'caption_model': 'model', 'caption_length': 'int', 'agreement': 'float'}

    def __init__(self, world_generator, world_captioner, caption_size, words, correct_ratio=None, train_correct_ratio=None, validation_correct_ratio=None, test_correct_ratio=None, caption_realizer=None, language=None):
        assert isinstance(caption_size, int) and caption_size > 0
        assert isinstance(words, list) and len(words) > 0
        super(CaptionAgreementDataset, self).__init__(world_size=world_generator.world_size, vectors=dict(caption=caption_size), words=words, language=language)
        self.world_generator = world_generator
        self.world_captioner = world_captioner
        self.caption_size = caption_size
        self.correct_ratio = util.value_or_default(correct_ratio, 0.5)
        self.train_correct_ratio = util.value_or_default(train_correct_ratio, self.correct_ratio)
        self.validation_correct_ratio = util.value_or_default(validation_correct_ratio, self.correct_ratio)
        self.test_correct_ratio = util.value_or_default(test_correct_ratio, self.correct_ratio)
        if isinstance(caption_realizer, CaptionRealizer):
            self.caption_realizer = caption_realizer
        else:
            assert caption_realizer is None or isinstance(caption_realizer, str)
            self.caption_realizer = CaptionRealizer.from_name(name=util.value_or_default(caption_realizer, 'dmrs'), language=util.value_or_default(language, 'english'))
        self.world_captioner.set_realizer(self.caption_realizer)

    def generate(self, n, mode=None, noise_range=None, include_model=False, alternatives=False):
        if mode == 'train':
            correct_ratio = self.train_correct_ratio
        elif mode == 'validation':
            correct_ratio = self.validation_correct_ratio
        elif mode == 'test':
            correct_ratio = self.test_correct_ratio
        else:
            correct_ratio = self.correct_ratio

        batch = self.zero_batch(n, include_model=include_model, alternatives=alternatives)
        captions = [None] * n
        for i in range(n):
            correct = random() < correct_ratio
            resample = 0
            while resample >= 0:
                self.world_generator.sample_values(mode=mode)
                if resample % self.__class__.RESAMPLE_CAPTIONER == 0:
                    # if resample > 0:
                    #     print(self.world_captioner.correct, self.world_captioner.model())
                    #     exit(0)
                    self.world_captioner.sample_values(mode=mode, correct=correct)
                resample += 1

                while True:
                    world = self.world_generator()
                    if world is not None:
                        break

                for attempt in range(self.__class__.MAX_ATTEMPTS):
                    caption = self.world_captioner(entities=world.entities)
                    if caption is not None:
                        # print('captioner successful:', resample, attempt, self.world_captioner.correct)
                        resample = -1
                        break
                # else:
                #     print('captioner failed')

            assert (caption.agreement(entities=world.entities) > 0.0 and correct) or (caption.agreement(entities=world.entities) < 0.0 and not correct)
            batch['world'][i] = world.get_array(noise_range=noise_range)
            captions[i] = caption
            batch['agreement'][i] = float(correct)
            if include_model:
                batch['world_model'][i] = world.model()
                batch['caption_model'][i] = caption.model()

        captions = self.caption_realizer.realize(captions=captions)
        unknown = self.words['[UNKNOWN]']
        missing_words = set()  # for assert
        max_caption_size = self.caption_size  # for assert
        for i, caption in enumerate(captions):
            if len(caption) > self.caption_size:
                if len(caption) > max_caption_size:
                    max_caption_size = len(caption)
                continue
            for w, word in enumerate(caption):
                if word not in self.words:
                    missing_words.add(word)
                    continue
                batch['caption'][i][w] = self.words.get(word, unknown)
            batch['caption_length'][i] = len(caption)
        assert not missing_words, 'Words missing in vocabulary: \'{}\''.format('\', \''.join(sorted(missing_words)))
        assert max_caption_size <= self.caption_size, 'Caption size exceeds max size: {} > {}'.format(max_caption_size, self.caption_size)

        return batch

    def get_html(self, generated, id2word):
        captions = generated['caption']
        caption_lengths = generated['caption_length']
        agreements = generated['agreement']
        data_html = list()
        for n, (caption, caption_length, agreement) in enumerate(zip(captions, caption_lengths, agreements)):
            if agreement == 1.0:
                agreement = 'correct'
            elif agreement == 0.0:
                agreement = 'incorrect'
            else:
                agreement = 'ambiguous'
            data_html.append('<div class="{agreement}"><div class="world"><img src="world-{world}.bmp" alt="world-{world}.bmp"></div><div class="caption"><p>{caption}</p></div></div>'.format(
                agreement=agreement,
                world=n,
                caption=util.tokens2string(id2word[word] for word in caption[:caption_length])
            ))
        html = '<!DOCTYPE html><html><head><title>{dtype} {name}</title><style>.data{{width: 100%; height: 100%;}} .correct{{width: 100%; margin-top: 1px; margin-bottom: 1px; background-color: #BBFFBB;}} .incorrect{{width: 100%; margin-top: 1px; margin-bottom: 1px; background-color: #FFBBBB;}} .ambiguous{{width: 100%; margin-top: 1px; margin-bottom: 1px; background-color: #FFFFBB;}} .world{{height: {world_height}px; display: inline-block; vertical-align: middle;}} .caption{{display: inline-block; vertical-align: middle; margin-left: 10px;}}</style></head><body><div class="data">{data}</div></body></html>'.format(
            dtype=self.type,
            name=self.name,
            world_height=self.world_shape[0],
            data=''.join(data_html)
        )
        return html
