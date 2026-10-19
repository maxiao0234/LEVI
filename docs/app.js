'use strict';
const $ = (selector) => document.querySelector(selector);
const domainColors = ['#bd4c66','#b47c25','#32936f','#3983a7','#6472cb','#9470b5'];
const domainNames = ['Symbolic','Geometric','Topological','Layout','Quantitative','Procedural'];
let activeDomain = 0, activeCase = 0;
const chosenCases = new Map();
let examples = [];
const dialog = $('#image-dialog');
let imageTrigger = null;
function openImage(src, caption, trigger) {
  imageTrigger = trigger;
  $('#dialog-image').src = src;
  $('#dialog-image').alt = caption;
  $('#image-caption').textContent = caption;
  dialog.showModal();
  document.body.style.overflow = 'hidden';
}
function closeImage() { dialog.close(); }
$('#close-dialog').addEventListener('click', closeImage);
dialog.addEventListener('click', event => { if (event.target === dialog) closeImage(); });
dialog.addEventListener('close', () => { document.body.style.overflow = ''; imageTrigger?.focus(); });
document.addEventListener('click', event => {
  const button = event.target.closest('[data-zoom]');
  if (button) openImage(button.dataset.zoom, button.dataset.caption, button);
});
function imageCard(name, src, caption, verdict, reference=false) {
  const figure = document.createElement('figure');
  figure.className = `model-card${reference ? ' reference' : ''}`;
  const title = document.createElement('div'); title.className = 'model-name'; title.textContent = name;
  const button = document.createElement('button'); button.className = 'image-button';
  button.dataset.zoom = src; button.dataset.caption = caption; button.setAttribute('aria-label', `Enlarge ${caption}`);
  const img = document.createElement('img'); Object.assign(img, {src, alt:caption, width:960, height:960, loading:'lazy'});
  button.append(img);
  const label = document.createElement('figcaption');
  const badge = document.createElement('span');
  badge.className = reference ? 'reference-note' : `verdict ${verdict.toLowerCase()}`;
  badge.textContent = reference ? 'Identity schematic' : verdict;
  label.append(badge); figure.append(title, button, label); return figure;
}
function domainCases() { return examples.filter(item => item.domain === domainNames[activeDomain]); }
function renderCase(index, focus=false) {
  const items = domainCases();
  activeCase = (index + items.length) % items.length;
  chosenCases.set(domainNames[activeDomain], activeCase);
  const item = items[activeCase];
  document.querySelectorAll('[data-case]').forEach((button,i) => {
    button.setAttribute('aria-pressed', String(i===activeCase));
    if (focus && i===activeCase) button.focus();
  });
  $('#example-panel').setAttribute('aria-labelledby', `domain-${activeDomain} case-title`);
  $('#case-domain').textContent = item.domain;
  $('#case-title').textContent = item.title;
  $('#case-requirement').textContent = item.requirement;
  $('#case-evidence').textContent = item.evidence;
  $('#case-analysis').textContent = item.analysis;
  $('#case-prompt').textContent = item.prompt;
  $('#case-progress').textContent = `${activeCase+1} / ${items.length}`;
  $('#previous-case').setAttribute('aria-label', `Previous ${item.domain} example`);
  $('#next-case').setAttribute('aria-label', `Next ${item.domain} example`);
  $('#previous-case').disabled = $('#next-case').disabled = items.length < 2;
  const grid = $('#model-grid'); grid.replaceChildren();
  grid.append(imageCard('Vector reference', item.reference, `${item.title}: identity reference schematic`, '', true));
  item.outputs.forEach(output => grid.append(imageCard(output.model, output.image, `${item.title} — ${output.model}; recorded ${output.verdict}`, output.verdict)));
  $('#example-status').textContent = `${item.domain}, example ${activeCase+1} of ${items.length}: ${item.title}. ${item.outputs.length} model outputs and one vector reference.`;
  $('.full-prompt').open = false;
}
function renderDomain(index, focus=false) {
  activeDomain = index;
  document.querySelectorAll('[data-domain]').forEach((button,i) => {
    button.setAttribute('aria-selected', String(i===index)); button.tabIndex = i===index ? 0 : -1;
    if (focus && i===index) button.focus();
  });
  const picker = $('#case-picker'); picker.replaceChildren();
  const items = domainCases();
  items.forEach((item,i) => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'case-choice';
    button.dataset.case = i; button.setAttribute('aria-controls','example-panel');
    button.setAttribute('aria-label',`${i+1}: ${item.title}`);
    const number = document.createElement('span'); number.className='case-number'; number.textContent=`0${i+1}`;
    const title = document.createElement('span'); title.className='case-choice-title'; title.textContent=item.tabTitle || item.title;
    button.append(number,title);
    button.addEventListener('click',()=>renderCase(i));
    button.addEventListener('keydown',event=>{
      let next;
      if(event.key==='ArrowRight')next=(i+1)%items.length;
      else if(event.key==='ArrowLeft')next=(i+items.length-1)%items.length;
      else if(event.key==='Home')next=0;
      else if(event.key==='End')next=items.length-1;
      else return;
      event.preventDefault();renderCase(next,true);
    });
    picker.append(button);
  });
  renderCase(chosenCases.get(domainNames[index]) || 0);
}
$('#previous-case').addEventListener('click',()=>renderCase(activeCase-1));
$('#next-case').addEventListener('click',()=>renderCase(activeCase+1));
async function loadExamples() {
  const response = await fetch('examples.json'); if (!response.ok) throw new Error('Examples unavailable');
  examples = await response.json();
  if (domainNames.some(domain=>!examples.some(item=>item.domain===domain))) throw new Error('Domain examples missing');
  const tabs = $('#domain-tabs');
  domainNames.forEach((domain,index) => {
    const button = document.createElement('button'); button.type = 'button'; button.id = `domain-${index}`;
    button.dataset.domain = index; button.setAttribute('role','tab'); button.setAttribute('aria-controls','example-panel');
    const dot = document.createElement('span'); dot.className = 'tab-dot'; dot.style.setProperty('--domain-color',domainColors[index]); dot.setAttribute('aria-hidden','true');
    const count=document.createElement('span');count.className='domain-count';count.textContent=examples.filter(item=>item.domain===domain).length;count.setAttribute('aria-hidden','true');button.setAttribute('aria-label',`${domain}, ${count.textContent} examples`);
    button.append(dot, document.createTextNode(domain), count); button.addEventListener('click',()=>renderDomain(index));
    button.addEventListener('keydown',event => {
      let next;
      if(event.key==='ArrowRight') next=(index+1)%domainNames.length;
      else if(event.key==='ArrowLeft') next=(index+domainNames.length-1)%domainNames.length;
      else if(event.key==='Home') next=0;
      else if(event.key==='End') next=domainNames.length-1;
      else return;
      event.preventDefault();renderDomain(next,true);
    });
    tabs.append(button);
  });
  renderDomain(activeDomain);
}
loadExamples().catch(()=> { $('#example-panel').textContent='Examples could not be loaded. Please reload, or see the complete comparisons in the paper.'; });
let results = [], metric = 0, descending = true;
const metricNames = ['Overall','Symbolic','Geometric','Topological','Layout','Quantitative','Procedural'];
function renderResults() {
  const body = $('#results-body'); body.replaceChildren();
  [...results].sort((a,b) => (descending ? b.values[metric]-a.values[metric] : a.values[metric]-b.values[metric]) || b.values[0]-a.values[0]).forEach((row,index) => {
    const tr=document.createElement('tr');
    const rankNumber=1+results.filter(other=>other.values[metric]>row.values[metric]).length;
    tr.classList.toggle('top-ranked',rankNumber===1);
    const rank=document.createElement('td');
    if(rankNumber<=3){
      const medal=['gold','silver','bronze'][rankNumber-1];
      tr.classList.add(`rank-${medal}`);
      const icon=document.createElement('span');icon.className='rank-symbol';icon.textContent=['🥇','🥈','🥉'][rankNumber-1];
      icon.setAttribute('role','img');icon.setAttribute('aria-label',`${medal} medal, rank ${rankNumber}`);rank.append(icon);
    }else rank.textContent=rankNumber;
    tr.append(rank);
    const name=document.createElement('td');name.textContent=row.model;tr.append(name);
    row.values.forEach((value,column)=>{const td=document.createElement('td');td.textContent=value.toFixed(2);if(column===metric)td.className='selected';tr.append(td);});
    body.append(tr);
  });
  document.querySelectorAll('[data-sort]').forEach(button=>{
    const selected=Number(button.dataset.sort)===metric;
    button.parentElement.removeAttribute('aria-sort');
    if(selected)button.parentElement.setAttribute('aria-sort',descending?'descending':'ascending');
    button.querySelector('span').textContent=selected?(descending?'↓':'↑'):'↕';
  });
  $('#result-status').textContent=`10 configurations · ${metricNames[metric]}, ${descending?'highest first':'lowest first'} · Paper results`;
}
document.querySelectorAll('[data-sort]').forEach(button=>button.addEventListener('click',()=>{const next=Number(button.dataset.sort);descending=next===metric?!descending:true;metric=next;renderResults();}));
fetch('results.json').then(response=>{if(!response.ok)throw new Error();return response.json();}).then(data=>{results=data;renderResults();}).catch(()=>{$('#result-status').textContent='Results could not be loaded. Please reload the page.';});
