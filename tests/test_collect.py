import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError

spec = importlib.util.spec_from_file_location('collector', Path(__file__).resolve().parents[1] / 'scripts/collect.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def sample_issue(number=1, title='[등록] 운영자 테스트 / tester'):
    return {'number': number, 'title': title, 'state': 'open', 'labels': [{'name': 'approved'}],
            'user': {'id': 123, 'login': 'tester'}, 'html_url': f'https://github.com/owner/clubs/issues/{number}',
            'body': f'### 동아리명\n\n운영자 테스트\n\n### GitHub ID\n\ntester\n\n### 공개 저장소\n\nhttps://github.com/owner/project\n\n### 시작일\n\n2026-09-01\n\n### 종료일\n\n2026-09-30\n\n### 공개 및 수집 확인\n\n- [x] {c.CONSENT}'}


class CollectorTests(unittest.TestCase):
    def approval(self, state, issue, issues=(), action='labeled'):
        c.update_approval(state, {'action': action, 'label': {'name': 'approved'},
                                 'issue': copy.deepcopy(issue), 'sender': {'login': 'owner'}}, issues)

    def pair(self):
        reg = sample_issue()
        reg['updated_at'] = '2026-09-08T01:00:00Z'
        perf = sample_issue(2, '[성과] 문서 작성')
        perf['updated_at'] = '2026-09-08T02:00:00Z'
        perf['body'] = f'### 등록 이슈 번호\n1\n### 활동일\n2026-09-08\n### 수행 내용과 본인 역할\n문서 작성\n### 증빙 링크\nhttps://github.com/owner/project\n### 공개 확인\n- [x] {c.PERFORMANCE_CONSENT}'
        state = {'approvals': {}, 'activities': {}}
        self.approval(state, reg)
        self.approval(state, perf, [reg, perf])
        return reg, perf, state

    def empty_api(self):
        class EmptyAPI:
            def request(self, path): return {'private': False, 'default_branch': 'main'}
            def pages(self, path, params=None): return iter([])
        return EmptyAPI()

    def test_performance_bound_to_registration_revision(self):
        for old, new in [('운영자 테스트', '새 동아리'), ('owner/project', 'owner/other'),
                         ('2026-09-01', '2026-09-02')]:
            with self.subTest(change=new):
                reg, perf, state = self.pair()
                run = lambda: c.collect(self.empty_api(), [reg, perf], state, {'test_accounts': []}, 'owner/clubs')
                self.assertEqual(len(run()['submissions']), 1)
                reg['body'] = reg['body'].replace(old, new)
                reg['updated_at'] = '2026-09-08T03:00:00Z'
                self.approval(state, reg, action='edited')
                self.assertEqual(run()['submissions'], [])
                self.approval(state, reg)
                result = run()
                self.assertEqual(result['submissions'], [])
                self.assertEqual(result['pending'], 1)
                self.assertTrue(any('재승인' in n for n in result['notices']))
                perf['updated_at'] = '2026-09-08T04:00:00Z'
                self.approval(state, perf, action='unlabeled')
                self.approval(state, perf, [reg, perf])
                self.assertEqual(len(run()['submissions']), 1)

    def test_legacy_performance_requires_review(self):
        reg, perf, state = self.pair()
        del state['approvals']['2']['registration_digest']
        result = c.collect(self.empty_api(), [reg, perf], state, {'test_accounts': []}, 'owner/clubs')
        self.assertEqual(result['submissions'], [])
        self.assertEqual(result['pending'], 1)

    def test_delayed_approval_does_not_bind_to_later_registration(self):
        reg, perf, state = self.pair()
        reg['body'] += '\nnew version'
        reg['updated_at'] = '2026-09-08T03:00:00Z'
        self.approval(state, reg)
        self.approval(state, perf, [reg, perf])
        self.assertIsNone(state['approvals']['2']['registration_digest'])

    def test_old_events_do_not_undo_newer_approval_and_sequence(self):
        reg, _, state = self.pair()
        old_event = copy.deepcopy(reg)
        reg['updated_at'] = '2026-09-08T03:00:00Z'
        self.approval(state, reg, action='edited')
        self.assertFalse(c.approved(reg, state['approvals']))
        reg['updated_at'] = '2026-09-08T04:00:00Z'
        self.approval(state, reg)
        self.approval(state, old_event, action='unlabeled')
        self.assertTrue(c.approved(reg, state['approvals']))
        reg['updated_at'] = '2026-09-08T05:00:00Z'
        self.approval(state, reg, action='closed')
        self.assertFalse(c.approved(reg, state['approvals']))
        self.approval(state, reg, action='reopened')
        self.assertFalse(c.approved(reg, state['approvals']))

    def test_changed_registration_discards_prior_collection_scope(self):
        reg, perf, state = self.pair()
        run = lambda: c.collect(self.empty_api(), [reg, perf], state, {'test_accounts': []}, 'owner/clubs')
        run()
        state['activities']['old'] = {'registration': 1, 'repository': 'owner/project'}
        self.assertEqual(len(run()['activities']), 1)
        reg['body'] = reg['body'].replace('owner/project', 'owner/other')
        reg['updated_at'] = '2026-09-08T03:00:00Z'; self.approval(state, reg)
        self.assertEqual(run()['activities'], [])

    def test_network_timeout_json_and_partial_pagination(self):
        api = c.API('')
        for error in [URLError('offline'), TimeoutError()]:
            with patch.object(c, 'urlopen', side_effect=error):
                with self.assertRaisesRegex(RuntimeError, '네트워크'): api.request('/test')
        with patch.object(c, 'urlopen') as mock:
            mock.return_value.__enter__.return_value.read.return_value = b'not json'
            with self.assertRaisesRegex(RuntimeError, '응답 형식'): api.request('/test')
        reg, _, state = self.pair()
        state['activity_scopes'] = {'1': c.digest(reg)}
        state['activities']['old'] = {'registration': 1, 'id': 'old'}
        def partial(*args):
            yield {'registration': 1, 'id': 'new'}
            raise RuntimeError('second page failed')
        with patch.object(c, 'activities', side_effect=partial):
            result = c.collect(api, [reg], state, {'test_accounts': []}, 'owner/clubs')
        self.assertEqual(len(result['activities']), 2)
        self.assertIn('확인 필요', result['registrations'][0]['status'])

    def test_registration_requires_same_account_and_consent(self):
        issue = sample_issue()
        self.assertTrue(c.registration(issue, ['tester'])['test'])
        issue['body'] = issue['body'].replace('### GitHub ID\n\ntester', '### GitHub ID\n\nother')
        with self.assertRaises(ValueError): c.registration(issue, [])
        issue = sample_issue(); issue['body'] = issue['body'].replace('[x]', '[ ]')
        with self.assertRaises(ValueError): c.registration(issue, [])

    def test_repository_validation(self):
        self.assertEqual(c.repository_name('https://github.com/owner/repo/'), 'owner/repo')
        for bad in ['https://evil.test/a/b', 'owner/../secret', 'owner/repo?token=x', 'owner/..', '/etc/passwd']:
            with self.assertRaises(ValueError): c.repository_name(bad)

    def test_duplicate_fields_rejected(self):
        with self.assertRaises(ValueError): c.fields('### GitHub ID\nfirst\n### GitHub ID\nsecond')

    def test_approval_invalidated_by_edits_and_close(self):
        issue = sample_issue(); state = {'approvals': {}}
        event = {'action': 'labeled', 'label': {'name': 'approved'}, 'issue': issue, 'sender': {'login': 'owner'}}
        c.update_approval(state, event)
        self.assertTrue(c.approved(issue, state['approvals']))
        edit = copy.deepcopy(issue); edit['body'] += '\nchanged'
        self.assertFalse(c.approved(edit, state['approvals']))
        edit = copy.deepcopy(issue); edit['title'] += ' changed'
        self.assertFalse(c.approved(edit, state['approvals']))
        issue['state'] = 'closed'
        self.assertFalse(c.approved(issue, state['approvals']))

    def test_korean_date_boundary(self):
        reg = {'start': '2026-09-01', 'end': '2026-09-01'}
        self.assertTrue(c.in_period('2026-08-31T15:00:00Z', reg))
        self.assertFalse(c.in_period('2026-08-31T14:59:59Z', reg))
        self.assertFalse(c.in_period('2026-09-01T15:00:00Z', reg))

    def test_manual_submission_author_and_safe_links(self):
        reg = c.registration(sample_issue(), [])
        issue = sample_issue(2, '[성과] 문서 작성')
        issue['body'] = f'### 등록 이슈 번호\n1\n### 활동일\n2026-09-08\n### 수행 내용과 본인 역할\n문서 작성\n### 증빙 링크\nhttps://github.com/owner/project\n### 공개 확인\n- [x] {c.PERFORMANCE_CONSENT}'
        self.assertEqual(c.performance(issue, [reg])['registration'], 1)
        issue['user']['id'] = 456
        with self.assertRaises(ValueError): c.performance(issue, [reg])
        self.assertFalse(c.public_url('javascript:alert(1)'))
        self.assertFalse(c.public_url('https://user:secret@example.com'))

    def test_pr_not_double_counted_as_issue(self):
        class MockAPI:
            def request(self, path): return {'private': False, 'default_branch': 'main'}
            def pages(self, path, params=None):
                if path.endswith('/commits'): return iter([])
                if path.endswith('/pulls'): return iter([{'number': 3, 'updated_at': '2026-09-08T00:00:00Z', 'created_at': '2026-09-08T00:00:00Z', 'user': {'id': 123}, 'html_url': 'https://github.com/owner/project/pull/3', 'title': 'PR', 'state': 'closed', 'merged_at': '2026-09-09T00:00:00Z'}])
                if path.endswith('/reviews'): return iter([])
                return iter([{'pull_request': {}, 'user': {'id': 123}, 'created_at': '2026-09-08T00:00:00Z'}])
        rows = list(c.activities(MockAPI(), c.registration(sample_issue(), [])))
        self.assertEqual([r['type'] for r in rows], ['pr'])
        self.assertEqual(rows[0]['state'], 'merged')

    def test_collection_failure_is_not_success_and_closed_registration_removed(self):
        class BrokenAPI:
            def request(self, path): raise RuntimeError('HTTP 403')
        issue = sample_issue(); state = {'approvals': {'1': {'digest': c.digest(issue)}}, 'activities': {}}
        output = c.collect(BrokenAPI(), [issue], state, {'test_accounts': []}, 'owner/clubs')
        self.assertIn('확인 필요', output['registrations'][0]['status'])
        self.assertTrue(output['notices'])
        state['activities']['old'] = {'registration': 1}
        issue['state'] = 'closed'
        output = c.collect(BrokenAPI(), [issue], state, {'test_accounts': []}, 'owner/clubs')
        self.assertEqual(output['activities'], [])

    def test_duplicate_registration_and_page_limit(self):
        class BrokenAPI:
            def request(self, path): raise RuntimeError('offline')
        one = sample_issue(); two = sample_issue(2)
        state = {'approvals': {str(i['number']): {'digest': c.digest(i)} for i in [one, two]}, 'activities': {}}
        output = c.collect(BrokenAPI(), [one, two], state, {'test_accounts': []}, 'owner/clubs')
        self.assertEqual(len(output['registrations']), 1)
        self.assertTrue(any('중복' in n for n in output['notices']))
        api = c.API('', max_pages=1); api.request = lambda *a: [{}] * 100
        with self.assertRaises(RuntimeError): list(api.pages('/test'))


if __name__ == '__main__': unittest.main()
