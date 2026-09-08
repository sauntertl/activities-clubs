const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.join(__dirname,'..');
const source=fs.readFileSync(path.join(root,'site/app.js'),'utf8');
const html=fs.readFileSync(path.join(root,'site/index.html'),'utf8');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.value='';this.checked=false;this.dataset={};this.attrs={};this.listeners={};this.classList={add:()=>{}};this.textContent='';}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,fn){this.listeners[k]=fn;}
  setCustomValidity(v){this.validationMessage=v;}
  focus(){this.focused=true;}
}
const record={id:1,login:'student',club:'개발',repository:'owner/repo',start:'2026-09-01',end:'2026-09-30',url:'https://github.com/owner/repo/issues/1',status:'수집 완료',test:false};
const sample={config:{title:'활동',subtitle:'기록'},repository:'owner/clubs',pending:0,notices:[],registrations:[record,{...record,id:2,login:'tester',test:true,club:'시험'}],activities:[{...record,type:'commit',date:'2026-09-08T00:00:00Z',title:'README 작업'},{...record,login:'tester',test:true,club:'시험',type:'issue',date:'2026-09-08T00:00:00Z',title:'시험 기록'}],submissions:[]};
async function app(response=sample,ok=true){
  const nodes=Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element()]));
  const tabs=['auto','manual','people'].map(t=>{const n=nodes['tab-'+t];n.dataset.tab=t;return n;});
  nodes.tests.checked=true;
  for(const k of ['m-people','m-repos','m-auto','m-manual','count'])nodes[k].textContent='—';
  const document={getElementById:id=>nodes[id],createElement:tag=>new Element(tag),querySelectorAll:()=>tabs};
  const context=vm.createContext({document,URL,Intl,Date,Option:class extends Element{constructor(text,value){super('option');this.textContent=text;this.value=value;}},setTimeout,fetch:async()=>({ok,status:503,json:async()=>structuredClone(response)})});
  vm.runInContext(source,context);await new Promise(resolve=>setImmediate(resolve));
  return {nodes,tabs,context,run:code=>vm.runInContext(code,context)};
}
test('reversed dates show accessible error and recover',async()=>{
 const a=await app();a.nodes.from.value='2026-09-10';a.nodes.to.value='2026-09-01';a.run('render()');
 assert.equal(a.nodes.from.attrs['aria-invalid'],'true');assert.match(a.nodes['date-error'].textContent,/시작일/);assert.equal(a.nodes['m-auto'].textContent,'—');
 assert.equal(a.nodes.from.max,'2026-09-01');assert.equal(a.nodes.to.min,'2026-09-10');
 a.nodes.from.value='2026-09-01';a.nodes.to.value='2026-09-10';a.run('render()');
 assert.equal(a.nodes.from.validationMessage,'');assert.equal(a.nodes['date-error'].hidden,true);assert.equal(a.nodes['m-auto'].textContent,2);
});
test('club, search, date and operator filters combine',async()=>{
 const a=await app();a.nodes.tests.checked=false;a.nodes.club.value='개발';a.nodes.search.value='readme';a.nodes.from.value='2026-09-08';a.nodes.to.value='2026-09-08';a.run('render()');
 assert.equal(a.nodes['m-auto'].textContent,1);assert.equal(a.nodes.panel.children.length,1);
 a.nodes.club.value='시험';a.run('render()');assert.equal(a.nodes['m-auto'].textContent,0);
});
test('keyboard tabs select and focus the next panel',async()=>{
 const a=await app();let prevented=false;a.tabs[0].listeners.keydown({key:'ArrowRight',preventDefault(){prevented=true;}});
 assert.ok(prevented);assert.equal(a.tabs[1].attrs['aria-selected'],'true');assert.equal(a.nodes.panel.attrs['aria-labelledby'],'tab-manual');assert.ok(a.tabs[1].focused);
 a.tabs[1].listeners.keydown({key:'End',preventDefault(){}});assert.equal(a.tabs[2].tabIndex,0);
});
test('untrusted titles are text and unsafe links stay inactive',async()=>{
 const a=await app();assert.equal(a.run("safeLink('javascript:alert(1)','x').href"),undefined);
 assert.equal(a.run("safeLink('https://name:secret@example.com','x').href"),undefined);
 assert.equal(a.run("element('h3','<img src=x onerror=alert(1)>').textContent"),'<img src=x onerror=alert(1)>');
 assert.equal(a.run("safeLink('https://github.com','x').rel"),'noopener noreferrer');
});
test('HTTP and malformed payloads show failure, not zero activity',async()=>{
 for(const [value,ok] of [[sample,false],[{},true]]){const a=await app(value,ok);assert.match(a.nodes.status.textContent,/불러오지 못/);assert.equal(a.nodes['m-auto'].textContent,'—');}
});
test('shipped CSS has AA contrast and no blocking webfont import',()=>{
 const css=fs.readFileSync(path.join(root,'site/styles.css'),'utf8');assert.doesNotMatch(css,/@import|fonts\.googleapis/);
 const muted=css.match(/--muted:(#[a-f0-9]{6})/)[1];
 const luminance=hex=>{const rgb=hex.slice(1).match(/../g).map(x=>parseInt(x,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;};
 for(const bg of ['#f5f7f4','#eaf0ec','#ffffff'])assert.ok((luminance(bg)+.05)/(luminance(muted)+.05)>=4.5);
 assert.match(html,/rel="icon"[^>]+favicon.svg/);assert.ok(fs.existsSync(path.join(root,'site/favicon.svg')));
});
