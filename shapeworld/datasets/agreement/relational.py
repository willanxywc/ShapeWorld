from shapeworld.dataset import CaptionAgreementDataset
from shapeworld.generators import GenericGenerator
from shapeworld.captioners import CaptionerMixer, AttributesTypeCaptioner, SpatialRelationCaptioner, ComparisonRelationCaptioner, ExistentialCaptioner


class RelationalDataset(CaptionAgreementDataset):

    dataset_name = 'relational'

    def __init__(self, entity_counts, train_entity_counts, validation_entity_counts, test_entity_counts, validation_combinations, test_combinations, caption_size, words, language=None):
        world_generator = GenericGenerator(
            entity_counts=entity_counts,
            train_entity_counts=train_entity_counts,
            validation_entity_counts=validation_entity_counts,
            test_entity_counts=test_entity_counts,
            validation_combinations=validation_combinations,
            test_combinations=test_combinations
        )
        verb_captioner = CaptionerMixer(
            captioners=(
                SpatialRelationCaptioner(),
                ComparisonRelationCaptioner())
        )
        world_captioner = ExistentialCaptioner(
            restrictor_captioner=AttributesTypeCaptioner(),
            body_captioner=verb_captioner,
        )
        super(RelationalDataset, self).__init__(
            world_generator=world_generator,
            world_captioner=world_captioner,
            caption_size=caption_size,
            words=words,
            language=language
        )


dataset = RelationalDataset
RelationalDataset.default_config = dict(
    entity_counts=[5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    train_entity_counts=[5, 6, 7, 8, 9, 10, 11, 12, 14],
    validation_entity_counts=[13],
    test_entity_counts=[15],
    validation_combinations=[['square', 'red', 'solid'], ['triangle', 'green', 'solid'], ['circle', 'blue', 'solid']],
    test_combinations=[['rectangle', 'yellow', 'solid'], ['cross', 'magenta', 'solid'], ['ellipse', 'cyan', 'solid']],
    caption_size=14,
    words=['.', 'a', 'above', 'an', 'behind', 'below', 'bigger', 'black', 'blue', 'circle', 'closer', 'closest', 'cross', 'cyan', 'darker', 'ellipse', 'farther', 'farthest', 'from', 'front', 'green', 'in', 'is', 'left', 'lighter', 'magenta', 'of', 'pentagon', 'rectangle', 'red', 'right', 'semicircle', 'shape', 'smaller', 'square', 'than', 'the', 'to', 'triangle', 'white', 'yellow']
)
