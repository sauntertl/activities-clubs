"""Collect public GitHub evidence. Python standard library only; never execute issue text."""
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
CONSENT = 'GitHub ID, 동아리명, 지정 저장소의 공개 활동을 수집하고 이 페이지에 공개하는 것에 동의합니다.'
PERFORMANCE_CONSENT = '제출 내용과 링크는 공개 가능한 실제 본인 활동이며 공개 게시에 동의합니다.'
REPO = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]+$')
USER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]{0,38}$')


def digest(issue):
    value = json.dumps([issue.get('title', ''), issue.get('body') or '', issue['user']['id']], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def fields(body):
    parts = re.split(r'^### (.+?)\s*$', body or '', flags=re.M)
    result = {}
    for n in range(1, len(parts), 2):
        if parts[n] in result:
            raise ValueError('중복 입력 항목')
        result[parts[n]] = parts[n + 1].strip()
    return result


def repository_name(value):
    value = value.strip()
    if value.startswith('https://github.com/'):
        value = value[len('https://github.com/'):].rstrip('/')
    if not REPO.fullmatch(value) or any(x in ('.', '..') for x in value.split('/')):
        raise ValueError('공개 저장소 주소 형식 오류')
    return value


def registration(issue, tests):
    f = fields(issue['body'])
    login = f.get('GitHub ID', '').strip()
    author = issue['user']['login']
    if not USER.fullmatch(login) or login.lower() != author.lower():
        raise ValueError('GitHub ID는 제출 계정과 같아야 합니다')
    if not re.search(r'\[[xX]\] ' + re.escape(CONSENT), f.get('공개 및 수집 확인', '')):
        raise ValueError('공개 및 수집 동의가 필요합니다')
    start, end = date.fromisoformat(f['시작일']), date.fromisoformat(f['종료일'])
    if not 0 <= (end - start).days <= 366:
        raise ValueError('활동 기간은 시작일부터 최대 366일입니다')
    club = f.get('동아리명', '').strip()
    if not club or len(club) > 100:
        raise ValueError('동아리명을 확인해 주세요')
    return dict(id=issue['number'], login=author, user_id=issue['user']['id'], club=club,
                repository=repository_name(f['공개 저장소']), start=start.isoformat(), end=end.isoformat(),
                url=issue['html_url'], test=author.lower() in [x.lower() for x in tests])


def approved(issue, approvals):
    entry = approvals.get(str(issue['number']), {})
    return (issue['state'] == 'open' and any(x['name'] == 'approved' for x in issue['labels'])
            and entry.get('digest') == digest(issue))


def update_approval(state, event):
    issue = event.get('issue')
    if not issue:
        return
    number = str(issue['number'])
    if event.get('action') == 'labeled' and event.get('label', {}).get('name') == 'approved':
        state['approvals'][number] = {'digest': digest(issue), 'by': event['sender']['login']}
    elif event.get('action') in ('edited', 'closed') or (
        event.get('action') == 'unlabeled' and event.get('label', {}).get('name') == 'approved'
    ):
        state['approvals'].pop(number, None)


def in_period(value, reg):
    if not value:
        return False
    day = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(KST).date().isoformat()
    return reg['start'] <= day <= reg['end']


def public_url(value):
    try:
        u = urlparse(value)
        return u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password
    except ValueError:
        return False


def performance(issue, regs):
    f = fields(issue['body'])
    number = int(f.get('등록 이슈 번호', '').lstrip('#'))
    reg = next((r for r in regs if r['id'] == number), None)
    if not reg or issue['user']['id'] != reg['user_id']:
        raise ValueError('본인의 승인된 등록 번호가 필요합니다')
    day = date.fromisoformat(f['활동일']).isoformat()
    if not reg['start'] <= day <= reg['end']:
        raise ValueError('등록 기간 밖의 활동일입니다')
    if not re.search(r'\[[xX]\] ' + re.escape(PERFORMANCE_CONSENT), f.get('공개 확인', '')):
        raise ValueError('공개 확인이 필요합니다')
    links = [x.strip() for x in f.get('증빙 링크', '').splitlines() if x.strip()]
    if not links or len(links) > 20 or not all(public_url(x) for x in links):
        raise ValueError('증빙은 https 주소를 한 줄에 하나씩 입력합니다')
    summary = f.get('수행 내용과 본인 역할', '')
    if not summary or len(summary) > 5000:
        raise ValueError('수행 내용은 1~5000자로 입력합니다')
    return dict(id=issue['number'], registration=number, login=reg['login'], club=reg['club'],
                title=issue['title'], date=day, summary=summary, links=links, url=issue['html_url'],
                test=reg['test'], status='담당자 확인')


class API:
    def __init__(self, token, max_pages=10):
        self.token, self.max_pages, self.calls = token, max_pages, 0

    def request(self, path, params=None, method='GET', data=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('잘못된 API 경로')
        self.calls += 1
        if self.calls > 800:
            raise RuntimeError('실행당 조회 한도 도달; 일부 결과만 수집')
        url = 'https://api.github.com' + path + ('?' + urlencode(params) if params else '')
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'clubs-activity-collector'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        payload = json.dumps(data).encode() if data is not None else None
        if payload:
            headers['Content-Type'] = 'application/json'
        try:
            with urlopen(Request(url, data=payload, headers=headers, method=method), timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            raise RuntimeError(f'GitHub 조회 실패 HTTP {exc.code}: {path}') from None

    def pages(self, path, params=None):
        for page in range(1, self.max_pages + 1):
            rows = self.request(path, dict(params or {}, per_page=100, page=page))
            if not isinstance(rows, list):
                raise RuntimeError('예상하지 못한 API 응답')
            yield from rows
            if len(rows) < 100:
                return
        raise RuntimeError('페이지 조회 한도 도달; 일부 결과만 수집')


def activities(api, reg):
    repo = api.request('/repos/' + reg['repository'])
    if repo.get('private', True):
        raise ValueError('비공개 저장소는 공개 페이지 수집 대상에서 제외합니다')
    reg['branch'] = repo['default_branch']
    since = datetime.combine(date.fromisoformat(reg['start']), datetime.min.time(), KST).isoformat()
    until = datetime.combine(date.fromisoformat(reg['end']) + timedelta(days=1), datetime.min.time(), KST).isoformat()
    base = '/repos/' + reg['repository']
    def item(kind, key, title, url, when, **extra):
        return dict(id=kind + ':' + key, registration=reg['id'], login=reg['login'], club=reg['club'],
                    repository=reg['repository'], type=kind, title=title[:300], url=url, date=when,
                    test=reg['test'], **extra)
    for c in api.pages(base + '/commits', {'author': reg['login'], 'sha': reg['branch'], 'since': since, 'until': until}):
        when = c['commit']['author']['date']
        if in_period(when, reg) and (c.get('author') or {}).get('id') == reg['user_id']:
            yield item('commit', c['sha'], c['commit']['message'].splitlines()[0], c['html_url'], when)
    # Updated-order listing permits reviews of older PRs without relying on short-lived Events feeds.
    for p in api.pages(base + '/pulls', {'state': 'all', 'sort': 'updated', 'direction': 'desc'}):
        if p['updated_at'] < datetime.fromisoformat(since).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'):
            break
        if p['user']['id'] == reg['user_id'] and in_period(p['created_at'], reg):
            yield item('pr', p['html_url'], p['title'], p['html_url'], p['created_at'],
                       state='merged' if p.get('merged_at') else p['state'])
        for review in api.pages(base + f"/pulls/{p['number']}/reviews"):
            if (review.get('user') or {}).get('id') == reg['user_id'] and in_period(review.get('submitted_at'), reg):
                yield item('review', str(review['id']), p['title'], review['html_url'], review['submitted_at'])
    for issue in api.pages(base + '/issues', {'state': 'all', 'creator': reg['login'], 'since': since}):
        if 'pull_request' not in issue and issue['user']['id'] == reg['user_id'] and in_period(issue['created_at'], reg):
            yield item('issue', issue['html_url'], issue['title'], issue['html_url'], issue['created_at'])


def collect(api, issues, state, config, host):
    notices, regs, submissions, pending = [], [], [], 0
    for issue in issues:
        if 'pull_request' in issue or not issue['title'].startswith(('[등록]', '[성과]')):
            continue
        if not approved(issue, state['approvals']):
            if issue['state'] == 'open':
                pending += 1
            continue
        if issue['title'].startswith('[등록]'):
            try:
                reg = registration(issue, config['test_accounts'])
                if any((r['user_id'], r['repository'].lower()) == (reg['user_id'], reg['repository'].lower())
                       and r['start'] <= reg['end'] and reg['start'] <= r['end'] for r in regs):
                    raise ValueError('동일 계정·저장소의 등록 기간 중복: 먼저 등록한 건만 수집')
                regs.append(reg)
            except (ValueError, KeyError) as e:
                notices.append(f"등록 #{issue['number']}: {e}")
    valid_ids = {r['id'] for r in regs}
    state['activities'] = {k: v for k, v in state['activities'].items() if v['registration'] in valid_ids}
    for reg in regs:
        reg['status'] = '수집 완료'
        try:
            for row in activities(api, reg):
                state['activities'][str(reg['id']) + ':' + row['id']] = row
            reg['last_success'] = datetime.now(timezone.utc).isoformat()
        except (ValueError, RuntimeError, KeyError) as e:
            reg['status'] = '확인 필요 · 일부 기록일 수 있음'
            notices.append(f"등록 #{reg['id']}: {e}")
    for issue in issues:
        if issue['title'].startswith('[성과]') and approved(issue, state['approvals']):
            try:
                submissions.append(performance(issue, regs))
            except (ValueError, KeyError) as e:
                notices.append(f"성과 #{issue['number']}: {e}")
    return dict(generated_at=datetime.now(timezone.utc).isoformat(), repository=host, config=config,
                registrations=regs, activities=list(state['activities'].values()), submissions=submissions,
                notices=notices, pending=pending)


def main():
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    host = repository_name(os.environ['GITHUB_REPOSITORY'])
    api = API(os.environ.get('GITHUB_TOKEN', ''), config['max_pages'])
    state = json.loads((ROOT / 'data/state.json').read_text(encoding='utf-8'))
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    if event_path and os.environ.get('GITHUB_EVENT_NAME') == 'issues':
        update_approval(state, json.loads(Path(event_path).read_text(encoding='utf-8')))
    # Idempotent label setup; only the current application repository is modified.
    labels = list(api.pages('/repos/' + host + '/labels'))
    if 'approved' not in [x['name'] for x in labels]:
        api.request('/repos/' + host + '/labels', method='POST', data={
            'name': 'approved', 'color': '16866B', 'description': '담당자 확인 완료. 내용 수정 후에는 제거하고 다시 승인합니다.'})
    issues = sorted(api.pages('/repos/' + host + '/issues', {'state': 'all'}), key=lambda x: x['number'])
    output = collect(api, issues, state, config, host)
    for path, value in [('data/state.json', state), ('site/data.json', output)]:
        (ROOT / path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Registrations={len(output['registrations'])}; activities={len(output['activities'])}; notices={len(output['notices'])}")


if __name__ == '__main__':
    main()
