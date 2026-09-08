import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).resolve().parents[1] / 'scripts/collect.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def sample_issue(number=1, title='[등록] 운영자 테스트 / tester'):
    return {'number': number, 'title': title, 'state': 'open', 'labels': [{'name': 'approved'}],
            'user': {'id': 123, 'login': 'tester'}, 'html_url': f'https://github.com/owner/clubs/issues/{number}',
            'body': f'### 동아리명\n\n운영자 테스트\n\n### GitHub ID\n\ntester\n\n### 공개 저장소\n\nhttps://github.com/owner/project\n\n### 시작일\n\n2026-09-01\n\n### 종료일\n\n2026-09-30\n\n### 공개 및 수집 확인\n\n- [x] {c.CONSENT}'}


class CollectorTests(unittest.TestCase):
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
