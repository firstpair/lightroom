import copy
import unittest

from scripts.preview_pipeline import stage_context as m


def pin(name):
    return dict(path='/synthetic/' + name, bytes=10, sha256='a' * 64)


def fixture():
    claim = dict(id='a' * 32, phase='stage', records=[
        dict(key='key-%d' % i, source=pin('job-%d' % i)) for i in range(8)])
    sources = [pin('stage-code'), pin('stage-checker')]
    value = dict(schema=m.SCHEMA, claim=claim,
                 inputs=[dict(r, prior=pin('native-receipt')) for r in claim['records']],
                 priorNative=pin('native-receipt'), nativeDocument=pin('native-proof'),
                 checkpoint=pin('checkpoint'), build=pin('build'), sources=sources,
                 selectedEngine='Ox', selectedExecutable=pin('qualified-ox-engine'),
                 pairs=[[1, 2], [3, 4], [5, 6], [7, 8]], sourceCohortJobs=8,
                 engineStageJobs=2, stageWorkers=6, configuredPhotoCPUIndexes=list(range(8, 16)),
                 EXglobalRequired=True, nativeInvocationsPlanned=0,
                 originalPhotoPayloadReadsPlanned=0, readbackEncodedCopiesPlanned=32,
                 executionReleased=False, runtimeGrantAcquired=False)
    return value, copy.deepcopy(claim), copy.deepcopy(sources)


def validate(value, claim, sources):
    return m.validate(value, claim=claim, expected_build=pin('build'),
                      expected_sources=sources, expected_cpu_indexes=list(range(8, 16)),
                      expected_engine='Ox', expected_executable=pin('qualified-ox-engine'))


class StageContextTests(unittest.TestCase):
    def test_preparation_never_authorizes_execution_or_release(self):
        v, claim, sources = fixture()
        result = validate(v, claim, sources)
        self.assertTrue(result['prepared'])
        self.assertFalse(result['executionAuthorized'])
        self.assertFalse(result['resourceReleaseAuthorized'])

    def test_changed_dependencies_claim_inputs_or_limits_refuse(self):
        for kind in ('source', 'build', 'claim', 'prior', 'pair', 'cpu',
                     'count', 'bool_count', 'extra', 'execution', 'grant', 'io',
                     'engine', 'executable', 'double_engine_copies'):
            v, claim, sources = fixture()
            if kind == 'source': v['sources'][0]['sha256'] = 'b' * 64
            elif kind == 'build': v['build']['sha256'] = 'b' * 64
            elif kind == 'claim': v['claim']['records'].reverse()
            elif kind == 'prior': v['inputs'][0]['prior'] = pin('foreign')
            elif kind == 'pair': v['pairs'].reverse()
            elif kind == 'cpu': v['configuredPhotoCPUIndexes'] = list(range(8))
            elif kind == 'count': v['sourceCohortJobs'] = 2
            elif kind == 'bool_count': v['nativeInvocationsPlanned'] = False
            elif kind == 'extra': v['unreviewedAuthority'] = True
            elif kind == 'execution': v['executionReleased'] = True
            elif kind == 'grant': v['runtimeGrantAcquired'] = True
            elif kind == 'engine': v['selectedEngine'] = 'Rust'
            elif kind == 'executable': v['selectedExecutable'] = pin('unqualified-engine')
            elif kind == 'double_engine_copies': v['readbackEncodedCopiesPlanned'] = 64
            else: v['EXglobalRequired'] = False
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate(v, claim, sources)

    def test_partial_claim_and_duplicate_keys_refuse(self):
        for kind in ('partial', 'duplicate'):
            v, claim, sources = fixture()
            if kind == 'partial': claim['records'].pop()
            else: claim['records'][1]['key'] = claim['records'][0]['key']
            v['claim'] = copy.deepcopy(claim)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate(v, claim, sources)


if __name__ == '__main__':
    unittest.main()
