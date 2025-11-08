// attachments.js - async multi-file & folder upload + deletion
// Requirements:
// - Inputs with [type=file][multiple][webkitdirectory] or plain multiple file inputs
// - Wrapper element .ll-attachments with data-parent-type & data-parent-id
// - Delete buttons: .ll-attach-del[data-id]
// - CSRF via cookie 'csrftoken'

(function(){
  // Optional drag & drop enhancement
  let dragCounter = 0;
  function log(...a){ if(window.DEBUG_UPLOAD) console.log('[ATT]', ...a); }
  function getCookie(name){
    const m = document.cookie.match('(^|;)\\s*'+name+'\\s*=\\s*([^;]+)');
    return m ? decodeURIComponent(m.pop()) : ''; }
  const csrftoken = getCookie('csrftoken');

  function humanSize(bytes){
    if(bytes === 0) return '0 B';
    const k=1024, units=['B','KB','MB','GB','TB'];
    const i=Math.floor(Math.log(bytes)/Math.log(k));
    return (bytes/Math.pow(k,i)).toFixed(i?1:0)+' '+units[i];
  }

  function buildItem(a){
    const li=document.createElement('li');
    li.className='ll-attachment-item d-flex align-items-center justify-content-between py-2 border-bottom';
    li.dataset.id=a.id;
    const rel = a.relative_path ? ` <span class="text-muted small">(${a.relative_path})</span>`:'';
    const nameLink = a.is_text ? `<a href="/attachments/preview/${a.id}/">${a.name}</a>` : `<a href="${a.url}" target="_blank" rel="noreferrer">${a.name}</a>`;
    li.innerHTML = `
      <div class="d-flex align-items-center gap-3 flex-grow-1">
        <div class="ll-attach-icon text-muted">📎</div>
        <div class="ll-attach-meta">
          <div class="fw-semibold">${nameLink}${rel}</div>
          <div class="small text-muted" data-size>${humanSize(a.size)}</div>
        </div>
      </div>
      <div class="d-flex align-items-center gap-3 flex-shrink-0">
        <a class="small" href="${a.url}" download>下载</a>
        <button class="btn btn-sm btn-link text-danger ll-attach-del" data-id="${a.id}">删除</button>
      </div>`;
    return li;
  }

  async function uploadBatch(wrapper, files){
    const parentType=wrapper.dataset.parentType;
    const parentId=wrapper.dataset.parentId;
    if(!files.length) return;
    const list = wrapper.querySelector('.ll-attachment-list');
    const fd = new FormData();
    [...files].forEach((f,i)=>{
      fd.append('files', f, f.name);
      const rel = f.webkitRelativePath || f.relativePath || '';
      if(rel) fd.append(`relative_path[${i}]`, rel);
    });
    fd.append('parent_type', parentType);
    fd.append('parent_id', parentId);
    try{
      const resp = await fetch('/attachments/upload/', {
        method:'POST',
        headers:{'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest'},
        body: fd
      });
      if(!resp.ok){
        const t = await resp.text();
        throw new Error(t || resp.status);
      }
      const data = await resp.json();
      if(!data.ok) throw new Error('上传失败');
      data.files.forEach(f=>{ list.appendChild(buildItem(f)); });
    }catch(err){
      console.error('Upload error', err);
      alert('上传失败: '+ err.message);
    }
  }

  async function deleteItem(id, btn){
    if(!confirm('确认删除该附件？')) return;
    btn.disabled = true;
    try{
      const resp = await fetch(`/attachments/delete/${id}/`, {
        method:'POST',
        headers:{'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest'}
      });
      if(!resp.ok){
        throw new Error(await resp.text() || resp.status);
      }
      const li = btn.closest('.ll-attachment-item');
      if(li) li.remove();
    }catch(err){
      alert('删除失败: '+err.message);
    }finally{ btn.disabled=false; }
  }

  function enhanceWrapper(wrapper){
    const input = wrapper.querySelector('input[type=file]');
    if(!input) return;
    input.addEventListener('change', (e)=>{
      const files = e.target.files;
      if(files && files.length){
        uploadBatch(wrapper, files);
        input.value=''; // reset
      }
    });
    // Drag & drop zone
    wrapper.classList.add('ll-attachments-enhanced');
    wrapper.addEventListener('dragenter', (e)=>{
      e.preventDefault();
      dragCounter++;
      wrapper.classList.add('ll-drag-over');
    });
    wrapper.addEventListener('dragover', (e)=>{
      e.preventDefault();
    });
    wrapper.addEventListener('dragleave', (e)=>{
      dragCounter--;
      if(dragCounter<=0){ wrapper.classList.remove('ll-drag-over'); }
    });
    wrapper.addEventListener('drop', (e)=>{
      e.preventDefault();
      dragCounter=0;
      wrapper.classList.remove('ll-drag-over');
      const dt = e.dataTransfer;
      if(!dt) return;
      const files = dt.files;
      if(files && files.length){
        uploadBatch(wrapper, files);
      }
    });
  }

  function bindGlobalClicks(){
    document.addEventListener('click', (e)=>{
      const btn = e.target.closest('.ll-attach-del');
      if(btn){
        const id = btn.dataset.id; if(id) deleteItem(id, btn);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('.ll-attachments').forEach(enhanceWrapper);
    bindGlobalClicks();
  });
})();
