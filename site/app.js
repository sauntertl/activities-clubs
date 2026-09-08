'use strict';
const $ = id => document.getElementById(id);
let data, activeTab = 'auto';
const kind = {commit:'커밋',pr:'Pull Request',issue:'이슈',review:'코드 리뷰'};
function element(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n; }
function safeLink(url, text, cls) { const a=element('a',text,cls);try{const u=new URL(url);if(u.protocol==='https:'&&!u.username&&!u.password){a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';}}catch{}return a; }
function day(value) {if(!value)return '';if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value;return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date(value));}
function filtered(rows) {const q=$('search').value.trim().toLowerCase(),club=$('club').value,from=$('from').value,to=$('to').value;return rows.filter(r=>($('tests').checked||!r.test)&&(!club||r.club===club)&&(!q||[r.login,r.title,r.summary,r.club,r.repository].join(' ').toLowerCase().includes(q))&&(!from||day(r.date||r.end)>=from)&&(!to||day(r.date||r.start)<=to));}
function validDates() {
  const from=$('from'),to=$('to'),invalid=!!(from.value&&to.value&&from.value>to.value);
  from.max=to.value;to.min=from.value;
  const error=invalid?'시작일은 종료일보다 늦을 수 없습니다. 날짜를 수정해 주세요.':'';
  from.setCustomValidity(error);to.setCustomValidity(error);
  from.setAttribute('aria-invalid',String(invalid));to.setAttribute('aria-invalid',String(invalid));
  $('date-error').textContent=error;$('date-error').hidden=!invalid;
  return !invalid;
}
function render() {
  if(!validDates()) {
    ['m-people','m-repos','m-auto','m-manual','count'].forEach(id=>$(id).textContent='—');
    $('student-count').textContent='조회 기간 확인 필요';
    $('panel').replaceChildren(element('div','시작일과 종료일을 확인하면 활동 내역이 표시됩니다.','empty'));
    return;
  }
  if(!data)return;
  const regs=filtered(data.registrations),autos=filtered(data.activities),manual=filtered(data.submissions);
  $('m-people').textContent=new Set(regs.map(r=>r.login.toLowerCase())).size;
  $('student-count').textContent='학생 '+new Set(regs.filter(r=>!r.test).map(r=>r.login.toLowerCase())).size+'명 · 테스트 '+new Set(regs.filter(r=>r.test).map(r=>r.login.toLowerCase())).size+'명';
  $('m-repos').textContent=new Set(regs.map(r=>r.repository.toLowerCase())).size;$('m-auto').textContent=autos.length;$('m-manual').textContent=manual.length;
  const rows=activeTab==='auto'?autos:activeTab==='manual'?manual:regs;
  rows.sort((a,b)=>(b.date||b.start).localeCompare(a.date||a.start));
  $('count').textContent=rows.length+'건';$('panel').replaceChildren();
  $('explanation').textContent={auto:'등록 저장소의 GitHub 기록입니다. 자동 수집은 성과 심사 완료를 의미하지 않습니다.',manual:'학생이 설명과 증빙을 제출하고 담당자가 확인한 성과입니다.',people:'담당자가 승인한 계정과 수집 대상 저장소입니다. 등록 이슈를 닫으면 다음 갱신부터 제외됩니다.'}[activeTab];
  if(!rows.length){$('panel').append(element('div',activeTab==='auto'?'표시할 자동 수집 기록이 없습니다. 등록 승인·수집 상태와 검색 조건을 확인해 주세요.':activeTab==='manual'?'아직 확인된 제출 성과가 없습니다. 주요 활동과 증빙 링크를 제출해 주세요.':'표시할 참여 등록이 없습니다. 동아리 활동 등록부터 시작해 주세요.','empty'));return;}
  for(const r of rows){const card=element('article',undefined,'record');card.append(element('div',day(r.date||r.start),'date'));const content=element('div');if(r.test)content.append(element('span','운영자 테스트','badge test'));content.append(element('span',activeTab==='auto'?kind[r.type]||r.type:activeTab==='manual'?'담당자 확인':'등록 승인','badge type'));if(r.state)content.append(element('span',{merged:'병합됨',closed:'닫힘',open:'진행 중'}[r.state]||r.state,'badge'));content.append(element('h3',r.title||r.club+' / '+r.login));content.append(element('div',[r.club,'@'+r.login,r.repository].filter(Boolean).join(' · '),'meta'));if(r.summary)content.append(element('p',r.summary,'summary'));if(r.links){const links=element('div',undefined,'evidence');r.links.forEach((l,i)=>links.append(safeLink(l,'증빙 '+(i+1)+' ↗')));content.append(links);}if(activeTab==='people'){content.append(element('p',r.start+' ~ '+r.end+' · '+r.status,'meta'));if(r.branch)content.append(element('div','커밋 수집 브랜치: '+r.branch,'meta'));}card.append(content,safeLink(r.url,activeTab==='people'?'등록 보기 ↗':'원문 보기 ↗'));$('panel').append(card);}
}
function chooseTab(tab) {activeTab=tab;document.querySelectorAll('[role=tab]').forEach(b=>{const yes=b.dataset.tab===tab;b.setAttribute('aria-selected',String(yes));b.tabIndex=yes?0:-1;});$('panel').setAttribute('aria-labelledby','tab-'+tab);render();}
document.querySelectorAll('[role=tab]').forEach(b=>{b.addEventListener('click',()=>chooseTab(b.dataset.tab));b.addEventListener('keydown',e=>{const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(e.key))return;e.preventDefault();const tabs=['auto','manual','people'];let n=tabs.indexOf(activeTab);n=e.key==='Home'?0:e.key==='End'?2:(n+(e.key==='ArrowRight'?1:2))%3;chooseTab(tabs[n]);$('tab-'+tabs[n]).focus();});});
$('filters').addEventListener('submit',e=>e.preventDefault());$('filters').addEventListener('input',render);$('filters').addEventListener('change',render);$('filters').addEventListener('reset',()=>setTimeout(render,0));
fetch('data.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();}).then(result=>{
  if(!Array.isArray(result.registrations)||!Array.isArray(result.activities)||!Array.isArray(result.submissions))throw Error('Invalid data');data=result;
  $('title').textContent=data.config.title;document.title=data.config.title;$('subtitle').textContent=data.config.subtitle;
  if(/^[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(data.repository)){const base='https://github.com/'+data.repository;$('repository').href=base;$('profile').href='https://github.com/'+data.repository.split('/')[0];$('register').href=base+'/issues/new?template=01-register.yml';$('submit').href=base+'/issues/new?template=02-activity.yml';$('review').href=base+'/issues';$('operations').href=base+'/blob/main/docs/OPERATIONS.md';}
  $('status').textContent=data.generated_at?'마지막 갱신 '+new Date(data.generated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})+' · 등록·제출 확인 대기 '+data.pending+'건':'첫 자동 수집을 준비하고 있습니다.';
  if(data.generated_at&&Date.now()-new Date(data.generated_at)>8*24*3600000){$('status').textContent+=' · 갱신이 지연되고 있습니다.';$('status').classList.add('error');}
  $('test-note').hidden=!data.registrations.some(r=>r.test);
  for(const club of [...new Set(data.registrations.map(r=>r.club))].sort()){$('club').append(new Option(club,club));}
  for(const notice of data.notices||[])$('notices').append(element('li',notice));if(data.notices?.length){$('collection-notices').open=true;$('status').textContent+=' · 수집 확인 사항 '+data.notices.length+'건';}
  render();
}).catch(()=>{$('status').textContent='활동 정보를 불러오지 못했습니다. 잠시 후 새로고침하거나 저장소의 수집 상태를 확인해 주세요.';$('status').classList.add('error');$('panel').replaceChildren(element('div','데이터 연결을 확인할 수 없어 활동 건수를 표시하지 않습니다.','empty'));});
