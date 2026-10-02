/* LinkedIn JD saver (S1 helper, M11-adjacent).
 * Install: copy the minified bookmarklet at the bottom into a bookmark URL.
 * Flow: extract JD text -> showSaveFilePicker (Chromium) -> fallback Blob download.
 * Target folder: select data/jds/ in the picker; browser remembers it.
 * File format: "<Title>.txt" with "<Title>\n<URL>\n\n<Description>".
 * ingest.py::ingest_jds reads *.txt/*.md; stem becomes JD title; URL line is ignored by lexicon.
 */

(async function () {
  const div = document.querySelector('[id^="JobDetails_AboutTheJob_"]');
  if (!div) {
    alert('Could not find the job description block on this page.');
    return;
  }
  const btn = div.querySelector('[data-testid="expandable-text-button"]');
  if (btn) {
    btn.click();
    await new Promise((r) => setTimeout(r, 400));
  }
  const desc = div.innerText.trim();
  if (!desc) {
    alert('Job description block is empty.');
    return;
  }
  if (desc.includes('\u2026more') || desc.endsWith('more')) {
    if (!confirm('The description still looks truncated. Save anyway?')) return;
  }
  const title = document.title.replace(' | LinkedIn', '').trim() || 'linkedin_jd';
  const url = location.href;
  const content = `${title}\n${url}\n\n${desc}`;
  const safeName = title.replace(/[^a-z0-9]+/gi, '_').slice(0, 80) || 'linkedin_jd';

  // Option 2: native save picker (Chromium, secure context, user gesture).
  if (window.showSaveFilePicker) {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: `${safeName}.txt`,
        types: [{ description: 'Job description', accept: { 'text/plain': ['.txt'] } }],
      });
      const w = await handle.createWritable();
      await w.write(content);
      await w.close();
      return;
    } catch (e) {
      if (e && e.name === 'AbortError') return; // user cancelled
      // fall through to Blob download on any other error
    }
  }
  const blob = new Blob([content], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${safeName}.txt`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
})();

// MINIFIED BOOKMARKLET (paste as bookmark URL):
// javascript:(async function(){const d=document.querySelector('[id^="JobDetails_AboutTheJob_"]');if(!d){alert('Could not find the job description block on this page.');return;}const b=d.querySelector('[data-testid="expandable-text-button"]');if(b){b.click();await new Promise(r=>setTimeout(r,400));}const x=d.innerText.trim();if(!x){alert('Job description block is empty.');return;}if(x.includes('\u2026more')||x.endsWith('more')){if(!confirm('The description still looks truncated. Save anyway?'))return;}const t=(document.title.replace(' | LinkedIn','').trim()||'linkedin_jd');const c=`${t}\n${location.href}\n\n${x}`;const s=(t.replace(/[^a-z0-9]+/gi,'_').slice(0,80)||'linkedin_jd');if(window.showSaveFilePicker){try{const h=await window.showSaveFilePicker({suggestedName:s+'.txt',types:[{description:'Job description',accept:{'text/plain':['.txt']}}]});const w=await h.createWritable();await w.write(c);await w.close();return;}catch(e){if(e&&e.name==='AbortError')return;}}const o=new Blob([c],{type:'text/plain'});const a=document.createElement('a');a.href=URL.createObjectURL(o);a.download=s+'.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000);})();
