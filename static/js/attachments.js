// attachments.js - async multi-file & folder upload + deletion
// Requirements:
// - Inputs with [type=file][multiple][webkitdirectory] or plain multiple file inputs
// - Wrapper element .ll-attachments with data-parent-type & data-parent-id
// - Delete buttons: .ll-attach-del[data-id]
// - CSRF via cookie 'csrftoken'

(function(){
  // Optional drag & drop enhancement
  let dragCounter = 0;
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

  function buildItem(a, opts){
    const item=document.createElement('div');
    item.className='list-group-item list-group-item-action d-flex align-items-center ll-attachment-item';
    item.dataset.id=a.id;

    const icon = document.createElement('img');
    icon.className = 'll-attach-icon me-2';
    let iconName = 'file-earmark';
    if (a.is_image) iconName = 'file-image';
    else if (a.is_video) iconName = 'file-play';
    else if (a.is_audio) iconName = 'file-music';
    else if (a.is_text) iconName = 'file-text';
    // 使用后端注入的哈希化静态资源映射，避免 Manifest 模式下 404
    if (window.LL_ICON_URLS) {
      const map = {
        'file-image': 'file_image',
        'file-play': 'file_play',
        'file-music': 'file_music',
        'file-text': 'file_text',
        'file-earmark': 'file_earmark'
      };
      const key = map[iconName] || 'file_earmark';
      icon.src = window.LL_ICON_URLS[key] || window.LL_ICON_URLS.file_earmark;
    } else {
      // 开发模式降级为非哈希路径
      icon.src = `/static/img/icons/${iconName}.svg`;
    }
    icon.alt = iconName.split('-')[1];
    item.appendChild(icon);

  const link = document.createElement('a');
  // 文件名链接使用预览路由，与服务端渲染保持一致（点击进入预览页）
  link.href = '/attachments/preview/' + a.id + '/';
  link.className = 'flex-grow-1 text-decoration-none text-body attachment-link';
  link.textContent = a.name;
  item.appendChild(link);

  const sizeSpan = document.createElement('span');
  sizeSpan.className = 'text-muted small me-3';
  sizeSpan.textContent = humanSize(a.size);
  item.appendChild(sizeSpan);
  // 下载按钮（outline 绿色）
  // 根据上下文 decide 按钮：如果允许编辑（即处于新建/编辑上下文），显示删除按钮；否则显示下载按钮
  const canEdit = opts && opts.canEdit;
    if (canEdit) {
      const del = document.createElement('button');
      del.type = 'button';
      // 保持与服务端删除按钮类名兼容
      del.className = 'btn btn-sm btn-outline-danger me-2 ll-attach-del delete-attachment';
      del.textContent = '删除';
      del.dataset.id = a.id;
      item.appendChild(del);
    } else {
      const dl = document.createElement('a');
      dl.className='btn btn-sm btn-outline-success me-2';
      dl.textContent='下载';
      dl.href='/attachments/download/'+a.id+'/';
      item.appendChild(dl);
    }

    return item;
  }

  // Limit per-folder files (allowed max) and chunk size for each async request
  const MAX_FOLDER_UPLOAD_FILES = 10000;
  const UPLOAD_CHUNK_SIZE = 50; // max files per request
  const UPLOAD_CHUNK_MAX_BYTES = 2 * 1024 * 1024; // 2MB per request

  // Send a single chunk (FormData) to server and handle response (supports progress via XHR)
  async function sendChunk(wrapper, files){
    const parentType = wrapper.dataset.parentType;
    const parentId = wrapper.dataset.parentId;
    const fd = new FormData();
    const paths = [];
    [...files].forEach((f,i)=>{
      fd.append('files', f, f.name);
      // Preserve folder structure when available. Fall back to file name to avoid empty paths.
      const rel = f.webkitRelativePath || f.relativePath || f.name || '';
      const relClean = (rel || '').replace(/\\/g,'/').replace(/^\/+/, '');
      const lastMod = typeof f.lastModified === 'number' ? f.lastModified : 0;
      paths.push({name: f.name, size: f.size, lastModified: lastMod, path: relClean});
      // Always append a per-file relative_path index field (may be empty string), so server can map by index reliably.
      fd.append(`relative_path[${i}]`, relClean);
    });
    try{ fd.append('relative_paths_json', JSON.stringify(paths)); }catch(err){}
    fd.append('parent_type', parentType);
    fd.append('parent_id', parentId);
    const uploadSession = wrapper.dataset.uploadSession;
    if (uploadSession) fd.append('upload_session', uploadSession);
    if(!csrftoken) throw new Error('CSRF token not found');
    const MAX_RETRIES = 3;
    let lastErr = null;
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++){
      try{
        // Use XHR for upload progress
        const data = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', '/attachments/upload/', true);
          xhr.withCredentials = true;
          xhr.setRequestHeader('X-CSRFToken', csrftoken);
          xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
          xhr.upload.onprogress = function(e){
            if (e.lengthComputable) {
              const chunkProgress = e.loaded / e.total;
              const chunkBytesUploaded = Math.floor(e.loaded);
              document.dispatchEvent(new CustomEvent('ll:upload:chunkprogress', { detail: { wrapper: wrapper, chunkProgress: chunkProgress, chunkBytesUploaded: chunkBytesUploaded, momentum: e.loaded } }));
            }
          };
          xhr.onreadystatechange = function(){
            if (xhr.readyState === XMLHttpRequest.DONE) {
              if (xhr.status >= 200 && xhr.status < 300) {
                try{ const j = JSON.parse(xhr.responseText); resolve(j); } catch(e){ resolve({ ok: false, error: xhr.responseText }); }
              } else {
                reject(new Error(xhr.responseText || xhr.status));
              }
            }
          };
          xhr.onerror = function(){ reject(new Error('Network error')); };
          xhr.send(fd);
        });
        if (!data.ok) throw new Error(data.error || 'upload failed');
        return data;
      }catch(err){
        lastErr = err;
        // If it's a server rejection error like HTTP 400 with message indicating too many files, don't retry
        if (err && err.message && /Too many files|invalid parent_type|invalid parent_id|Failed to parse uploaded files|Request size may be too large|413/.test(err.message)){
          throw err;
        }
        // Backoff
        await new Promise(res => setTimeout(res, 500 * attempt));
      }
    }
    throw lastErr || new Error('Unknown upload error');
    if(!resp.ok){ const t = await resp.text(); throw new Error(t || resp.status); }
    const data = await resp.json();
    if(!data.ok) throw new Error(data.error || 'upload failed');
    return data;
  }

  async function uploadBatch(wrapper, files){
    // Ensure we have an upload_session id on the wrapper so server can associate async uploads
    try {
      if (!wrapper.dataset.uploadSession) {
        wrapper.dataset.uploadSession = 's'+Date.now().toString(36) + Math.random().toString(36).slice(2,8);
        try { document.dispatchEvent(new CustomEvent('ll:upload_session:set', { detail: { wrapper: wrapper } })); } catch (e) { }
      }
    } catch (e) { /* ignore */ }
    // If wrapper contains an input marked data-no-async or wrapper itself is marked, treat files as staged
    if (wrapper.querySelector('input[type=file][data-no-async]') || wrapper.hasAttribute('data-no-async')){
      try {
        const input = wrapper.querySelector('input[type=file][data-no-async]') || (wrapper.hasAttribute('data-no-async') ? wrapper.querySelector('input[type=file]') : null);
        if (input) renderStagedFiles(wrapper, files, input);
      } catch (err) { console.warn('uploadBatch staged fallback failed', err); }
      return;
    }

    const parentType=wrapper.dataset.parentType;
    const parentId=wrapper.dataset.parentId;
    if(!files.length) return;
    if(files.length > MAX_FOLDER_UPLOAD_FILES){
      alert('单次上传的文件数超过上限（' + MAX_FOLDER_UPLOAD_FILES + '），请减少文件或分批上传。');
      return;
    }
    // Chunk by size or count to avoid network/proxy/Django limits
    var totalBytes = 0;
    for (let f of files) totalBytes += (f.size || 0);
    // Initialize progress/disable UI
    try{ wrapper._upload_total = totalBytes; wrapper._upload_uploaded = 0; }catch(e){}
    if (!wrapper._upload_inflight) wrapper._upload_inflight = 0;
    wrapper._upload_inflight++;
    try{
      const form = wrapper.closest('form');
      if(form){ const btn = form.querySelector('button[type=submit], input[type=submit]'); if(btn) btn.disabled = true; }
    }catch(e){}
    document.dispatchEvent(new CustomEvent('ll:upload:start', {detail:{wrapper: wrapper, totalBytes: totalBytes}}));
    function setWrapperProgress(wrapper, percent){
      try{
        const pb = wrapper.querySelector('.ll-upload-progress');
        if(!pb) return;
        const bar = pb.querySelector('.progress-bar');
        if(!bar) return;
        if (isNaN(percent) || percent <= 0) { pb.classList.add('d-none'); pb.setAttribute('aria-hidden','true'); bar.style.width = '0%'; }
        else { pb.classList.remove('d-none'); pb.setAttribute('aria-hidden','false'); bar.style.width = Math.min(100, Math.round(percent)) + '%'; }
      }catch(e){}
    }
    function finishOneUpload(wrapper){ try{ wrapper._upload_inflight--; }catch(e){} if(!wrapper._upload_inflight || wrapper._upload_inflight <= 0){ try{ setWrapperProgress(wrapper, 100); }catch(e){} try{ setTimeout(()=>{ setWrapperProgress(wrapper, 0); }, 800); }catch(e){} const form = wrapper.closest('form'); if(form){ const btn = form.querySelector('button[type=submit], input[type=submit]'); if(btn) btn.disabled = false; } document.dispatchEvent(new CustomEvent('ll:upload:done', { detail: { wrapper: wrapper } })); }}
    if (totalBytes > UPLOAD_CHUNK_MAX_BYTES || files.length > UPLOAD_CHUNK_SIZE){
      console.debug(`[attachments] Uploading ${files.length} files in chunks (total ${totalBytes} bytes, chunk max ${UPLOAD_CHUNK_MAX_BYTES} bytes / ${UPLOAD_CHUNK_SIZE} files)`);
      const chunks = [];
      let curChunk = [];
      let curBytes = 0;
      for (let f of files){
        const fsize = f.size || 0;
        if ((curChunk.length > 0 && (curBytes + fsize > UPLOAD_CHUNK_MAX_BYTES)) || curChunk.length >= UPLOAD_CHUNK_SIZE){
          chunks.push(curChunk);
          curChunk = [];
          curBytes = 0;
        }
        curChunk.push(f);
        curBytes += fsize;
      }
      if (curChunk.length) chunks.push(curChunk);
      try{
      for (let chunk of chunks){
        // Compute chunk bytes
        const chunkTotal = chunk.reduce((s,f)=>s + (f.size || 0), 0);
        let handler = function(ev){};
        handler = function(ev){ if (ev.detail && ev.detail.wrapper === wrapper){
            const uploadedSoFar = wrapper._upload_uploaded || 0;
            const curChunkUploaded = (ev.detail.chunkProgress || 0) * chunkTotal;
            const percent = (uploadedSoFar + curChunkUploaded) / (totalBytes || 1) * 100;
            setWrapperProgress(wrapper, percent);
          }};
        document.addEventListener('ll:upload:chunkprogress', handler);
        // sendChunk now ensures relative_path JSON includes path fallback to file name
        const data = await sendChunk(wrapper, chunk);
        document.removeEventListener('ll:upload:chunkprogress', handler);
        wrapper._upload_uploaded = (wrapper._upload_uploaded || 0) + chunkTotal;
        setWrapperProgress(wrapper, (wrapper._upload_uploaded || 0) / (totalBytes || 1) * 100);
        // Insert returned items to UI
        const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;
        data.files.forEach(f=>{
          const canEdit = wrapper.dataset.canEdit && wrapper.dataset.canEdit !== '0' ? true : false;
          const newItem = buildItem(f, {canEdit: canEdit});
          let targetContainer = listContainer;
          if (f.relative_path && f.relative_path.includes('/')) targetContainer = ensureFolderPath(listContainer, f.relative_path) || listContainer;
          const inputContainer = (targetContainer === listContainer) ? listContainer.querySelector('.mt-2') : null;
          if (inputContainer) targetContainer.insertBefore(newItem, inputContainer); else targetContainer.appendChild(newItem);
        });
      }
      }catch(err){
        console.error('Upload chunked error', err);
        alert('上传失败: ' + (err.message || err));
        finishOneUpload(wrapper);
        return;
      }
      finishOneUpload(wrapper);
      return;
    }
    
    // Find the container for attachment items. It might be the wrapper itself
    // or a specific list inside it. Let's make it flexible.
    // The new structure uses the wrapper directly as the container for items.
  // 优先使用统一的包裹容器（保证所有条目外框一致）
  const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;

    // For single-chunk path, reuse sendChunk to centralize behavior
    try {
      const data = await sendChunk(wrapper, files);
      const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;
      data.files.forEach(f => {
        const canEdit = wrapper.dataset.canEdit && wrapper.dataset.canEdit !== '0' ? true : false;
        const newItem = buildItem(f, { canEdit: canEdit });
        let targetContainer = listContainer;
        if (f.relative_path && f.relative_path.includes('/')) {
          // ensureFolderPath expects a full path including filename; it will strip the filename
          targetContainer = ensureFolderPath(listContainer, f.relative_path) || listContainer;
        }
        const inputContainer = (targetContainer === listContainer) ? listContainer.querySelector('.mt-2') : null;
        if (inputContainer) targetContainer.insertBefore(newItem, inputContainer); else targetContainer.appendChild(newItem);
      });
      finishOneUpload(wrapper);
      return;
    } catch (err) {
      console.error('Upload error', err);
      alert('上传失败: ' + (err.message || err));
      finishOneUpload(wrapper);
      return;
    }
  }

  // Render staged (not-yet-uploaded) files from inputs that are not async-uploaded
  function renderStagedFiles(wrapper, files, input){
    if(!files || !files.length) return;
    const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;
    const canEdit = wrapper.dataset.canEdit && wrapper.dataset.canEdit !== '0';
    [...files].forEach((f, i)=>{
      const fake = {
        id: 'staged-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8),
        name: f.name,
        size: f.size,
        is_image: (/^image\//).test(f.type),
        is_video: (/^video\//).test(f.type),
        is_audio: (/^audio\//).test(f.type),
        is_text: (/^(text|application\/(json|xml|javascript|x-www-form-urlencoded))/).test(f.type),
        relative_path: (f.webkitRelativePath || f.relativePath || f.name).replace(/\\/g, '/').replace(/^\/+/, ''),
      };
      const el = buildItem(fake, {canEdit: canEdit});
      // For staged entries, disable preview link (no server id yet)
      const link = el.querySelector('.attachment-link');
      if(link){ link.removeAttribute('href'); link.classList.add('staged-link'); }
      el.classList.add('ll-attachment-staged');
      // Replace delete button text & behavior for staged items (remove from the input FileList)
      const stagedDel = el.querySelector('.delete-attachment') || el.querySelector('.ll-attach-del');
      if(stagedDel){
        stagedDel.textContent = '移除';
        stagedDel.addEventListener('click', (ev)=>{
          ev.stopPropagation();
          try{
            // Remove the file from the input.files via DataTransfer
            const dt = new DataTransfer();
            const curFiles = Array.from(input.files || []);
            for (let fi of curFiles){
              // Compare by filename + size; lastModified not available reliably on all browsers
              if (fi.name === f.name && (fi.size === f.size)){
                // skip this one (remove)
                continue;
              }
              dt.items.add(fi);
            }
            input.files = dt.files;
          }catch(err){
            console.warn('Unable to update file input after staged delete', err);
          }
          // Remove preview element
          const parent = el.parentElement;
          if(parent) parent.removeChild(el);
        }, {once: true});
      }
      let targetContainer = listContainer;
      if (fake.relative_path && fake.relative_path.includes('/')){
        targetContainer = ensureFolderPath(listContainer, fake.relative_path) || listContainer;
      }
      const inputContainer = (targetContainer === listContainer) ? listContainer.querySelector('.mt-2') : null;
      if (inputContainer) {
        targetContainer.insertBefore(el, inputContainer);
      } else {
        targetContainer.appendChild(el);
      }
    });
  }

  async function deleteItem(id, btn){
    if(!confirm('确认删除该附件？')) return;
    btn.disabled = true;
    try {
      const resp = await fetch(`/attachments/delete/${id}/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest','Accept':'application/json'}
      });
      if(!resp.ok){
          const raw = await resp.text();
          let errMsg = raw;
          try{ const parsed = JSON.parse(raw); errMsg = parsed.error || parsed.message || raw; }catch(e){}
          throw new Error(errMsg || resp.status);
      }
      const item = btn.closest('.ll-attachment-item');
      if(item) item.remove();
    } catch(err) {
      alert('删除失败: ' + err.message);
    } finally {
      btn.disabled = false;
    }
  }

  // 图标地址辅助
  function iconUrl(key){
    if (window.LL_ICON_URLS && window.LL_ICON_URLS[key]) return window.LL_ICON_URLS[key];
    const map = {
      folder: '/static/img/icons/folder.svg',
      caret_right: '/static/img/icons/caret-right.svg',
      caret_down: '/static/img/icons/caret-down.svg'
    };
    return map[key] || '';
  }
  // 创建单个文件夹行 + 子容器
  function createFolderRow(name, canEdit){
    const row = document.createElement('div');
    row.className='list-group-item list-group-item-action d-flex align-items-center ll-attachment-item ll-folder-row collapsed';
    row.dataset.folderName=name;
    const caret=document.createElement('img');
    caret.className='ll-caret-icon me-1';
    caret.src=iconUrl('caret_right');
    caret.alt='toggle';
    row.appendChild(caret);
    const folderIcon=document.createElement('img');
    folderIcon.className='ll-attach-icon me-2';
    folderIcon.src=iconUrl('folder');
    folderIcon.alt='folder';
    row.appendChild(folderIcon);
    const span=document.createElement('span');
    span.className='flex-grow-1';
    span.textContent=name;
    row.appendChild(span);
    const meta=document.createElement('span');
    meta.className='text-muted small ms-2 ll-folder-meta';
    meta.textContent='文件夹';
    row.appendChild(meta);
    // 如果父容器允许编辑（ll-attachments 有 data-can-edit），添加删除按钮
    if (canEdit) {
      const delBtn = document.createElement('button');
      delBtn.type='button';
      delBtn.className='btn btn-sm btn-outline-danger ms-2 ll-folder-del';
      delBtn.textContent='删除';
      // folder-path 在 ensureFolderPath 中再赋值（因为需要构造累计路径）
      row.appendChild(delBtn);
    }
    const children=document.createElement('div');
    children.className='list-group list-group-flush ms-4 ll-folder-children d-none mb-2';
    children.dataset.loaded = '0';
    children.dataset.folderPath = '';
    return {row,children};
  }
  // 确保路径上所有文件夹节点存在，返回最终子容器（用于放文件）
  function ensureFolderPath(rootContainer, relPath){
    const parts=(relPath||'').split('/').filter(Boolean);
    if(!parts.length) return rootContainer;
    // 最后一段是文件名，文件夹链是 slice(0,-1)
    const chain=parts.slice(0,-1);
    if(!chain.length) return rootContainer; // 没有文件夹
    let container=rootContainer;
    let accumulated='';
    for(const name of chain){
      let foundRow=null, foundChildren=null;
      for(let el=container.firstElementChild; el; el=el.nextElementSibling){
        if(el.classList && el.classList.contains('ll-folder-row') && el.dataset.folderName===name){
          foundRow=el; foundChildren=el.nextElementSibling; break;
        }
      }
      if(!foundRow){
        const canEdit = rootContainer.closest('.ll-attachments')?.dataset.canEdit;
        const created=createFolderRow(name, canEdit);
        const inputContainer=rootContainer===container?rootContainer.querySelector('.mt-2'):null;
        if(inputContainer){
          container.insertBefore(created.row,inputContainer);
          container.insertBefore(created.children,inputContainer);
        }else{
          container.appendChild(created.row);
          container.appendChild(created.children);
        }
        accumulated = accumulated ? (accumulated + '/' + name) : name;
        created.row.dataset.folderPath = accumulated;
        created.children.dataset.folderPath = accumulated;
        const delBtn = created.row.querySelector('.ll-folder-del');
        if(delBtn){ delBtn.dataset.folderPath = accumulated; }
        // 保持新建文件夹默认折叠，不展开
        container=created.children;
      }else{
        accumulated = accumulated ? (accumulated + '/' + name) : name;
        foundRow.dataset.folderPath = accumulated;
        if (foundChildren) foundChildren.dataset.folderPath = accumulated;
        const delBtn = foundRow.querySelector('.ll-folder-del');
        if(delBtn){ delBtn.dataset.folderPath = accumulated; }
        // 已存在也保持当前折叠状态
        container=foundChildren || container;
      }
    }
    return container;
  }

  function enhanceWrapper(wrapper){
    const inputs = wrapper.querySelectorAll('input[type=file]');
    if(!inputs || !inputs.length) return;
    // Threshold above which we auto-async-upload even if input is marked data-no-async
    const AUTO_ASYNC_THRESHOLD = 50; // files
    inputs.forEach((input)=>{
      if (input.hasAttribute && input.hasAttribute('data-no-async')){
        // For non-async inputs, add a preview renderer so users see staged files
        input.addEventListener('change', (e)=>{
          const files = e.target.files;
          if(files && files.length){
            // If the file count exceeds AUTO_ASYNC_THRESHOLD, perform async upload instead of staged.
                if (files.length > AUTO_ASYNC_THRESHOLD){
                  console.debug('[attachments] large folder selected, auto async uploading', files.length);
                  uploadBatch(wrapper, files).then(()=>{ input.value=''; }).catch(e=>{ console.warn('auto async upload failed', e); });
                } else {
              // Render staged preview without uploading
              renderStagedFiles(wrapper, files, input);
            }
            // Note: keep the input.files untouched until submit or staged delete if staged
          }
        });
      } else {
        input.addEventListener('change', (e)=>{
          const files = e.target.files;
            if(files && files.length){
            uploadBatch(wrapper, files).then(()=>{ input.value=''; }).catch(e=>{ console.warn('upload failed', e); input.value=''; });
          }
        });
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
        // If wrapper contains file inputs marked data-no-async, treat drop as staged and
        // render previews into the wrapper using the first such input; otherwise perform async upload.
        const noAsyncInput = wrapper.querySelector('input[type=file][data-no-async]') || (wrapper.hasAttribute('data-no-async')? wrapper.querySelector('input[type=file]') : null);
      if (noAsyncInput) {
        // When input is staged but file count is large, auto upload chunks to avoid large POSTs
        if (files.length > AUTO_ASYNC_THRESHOLD) {
          uploadBatch(wrapper, files).then(()=>{ try{ noAsyncInput.value=''; }catch(e){} }).catch(e=>{ console.warn('upload failed', e); });
        } else {
          renderStagedFiles(wrapper, files, noAsyncInput);
        }
          } else {
            uploadBatch(wrapper, files);
          }
      }
    });
  }

  function bindGlobalClicks(){
    document.addEventListener('click', (e)=>{
      // 附件删除（模板 class: ll-attach-del）
      const attDel = e.target.closest('.ll-attach-del') || e.target.closest('.delete-attachment');
      if(attDel){
        const id = attDel.dataset.id; if(id) deleteItem(id, attDel);
      }
      const folderDel = e.target.closest('.ll-folder-del');
      if(folderDel){
        const wrapper = folderDel.closest('.ll-attachments');
        if(!wrapper) return;
        const parentType = wrapper.dataset.parentType;
        const parentId = wrapper.dataset.parentId;
        const folderPath = folderDel.dataset.folderPath;
        if(!folderPath) return;
        if(!confirm(`确认删除文件夹及其所有文件？\n${folderPath}`)) return;
        const fd = new FormData();
        fd.append('parent_type', parentType);
        fd.append('parent_id', parentId);
        fd.append('folder_path', folderPath);
        fetch('/attachments/delete_folder/', {
          method:'POST',
          credentials: 'same-origin',
          headers:{'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
          body: fd
        }).then(async (r)=>{
          const text = await r.text();
          let res;
          try{ res = JSON.parse(text); } catch(e) { res = { ok: false, error: text }; }
          if(!res.ok){ alert('删除失败: '+(res.error||'未知错误')); return; }
          // 移除该文件夹行与其子内容容器
          const row = folderDel.closest('.ll-folder-row');
          if(row){
            const children = row.nextElementSibling;
            if(children && children.classList.contains('ll-folder-children')){
              children.remove();
            }
            row.remove();
          }
        }).catch(err=>{
          alert('删除失败: '+ err.message);
        });
      }
      const folderDl = e.target.closest('.ll-folder-dl');
      if(folderDl){
        e.stopPropagation();
        const wrapper = folderDl.closest('.ll-attachments');
        if(!wrapper) return;
        const parentType = wrapper.dataset.parentType;
        const parentId = wrapper.dataset.parentId;
        const folderPath = folderDl.dataset.folderPath;
        if(!folderPath) return;
        // 直接跳转下载链接
        const url = `/attachments/download_folder/?parent_type=${encodeURIComponent(parentType)}&parent_id=${encodeURIComponent(parentId)}&folder_path=${encodeURIComponent(folderPath)}`;
        window.location.href = url;
      }
    });
    // 评论删除（AJAX）：class delete-comment, data-id
    document.addEventListener('click', (e)=>{
      const btn = e.target.closest('.delete-comment');
      if(!btn) return;
      const id = btn.dataset.id;
      if(!id) return;
      if(!confirm('确认删除该评论？此操作不可撤销。')) return;
      btn.disabled = true;
      fetch(`/comments/${encodeURIComponent(id)}/delete/`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest','Accept':'application/json'}
      }).then(async r=>{
        if(!r.ok){ throw new Error(await r.text() || r.status); }
        // 成功：移除评论节点
        const node = btn.closest('.comment-item');
        if(node) node.remove();
      }).catch(err=>{
        alert('删除评论失败：'+err.message);
      }).finally(()=>{ btn.disabled = false; });
    });
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('.ll-attachments').forEach(enhanceWrapper);
    bindGlobalClicks();
    // 目录展开/折叠逻辑（简化版 — 取消动画，保证兼容性）
    document.addEventListener('click', (e) => {
      const row = e.target.closest('.ll-folder-row');
      if (!row) return;
      // 如果点击的是操作按钮（删除/下载）不要触发折叠
      if (e.target.closest('.ll-folder-del') || e.target.closest('.ll-folder-dl')) return;
      // 查找紧邻或后续的 .ll-folder-children 元素作为子容器
      let children = row.nextElementSibling;
      if (!children || !children.classList.contains('ll-folder-children')){
        let sib = row.nextElementSibling;
        children = null;
        while(sib){
          if (sib.classList && sib.classList.contains('ll-folder-children')){ children = sib; break; }
          sib = sib.nextElementSibling;
        }
      }
      if (!children) return;
      const caret = row.querySelector('.ll-caret-icon');
      const collapsed = row.classList.contains('collapsed');
      if (collapsed) {
        // If this folder's children haven't been loaded yet, fetch them lazily
        const loaded = children.dataset.loaded === '1';
        if (!loaded) {
          // fetch content via API
          const wrapper = row.closest('.ll-attachments');
          if (wrapper) {
            const parentType = wrapper.dataset.parentType;
            const parentId = wrapper.dataset.parentId;
            const folderPath = row.dataset.folderPath || row.dataset.folderName || '';
            // assemble form data
            const fd = new FormData();
            fd.append('parent_type', parentType);
            fd.append('parent_id', parentId);
            fd.append('folder_path', folderPath);
            const upload_session = wrapper.dataset.uploadSession;
            if (upload_session) fd.append('upload_session', upload_session);
            fetch('/attachments/list_folder/', {
              method: 'POST',
              credentials: 'same-origin',
              headers: {'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest','Accept':'application/json'},
              body: fd
            }).then(async r => {
              const raw = await r.text();
              let res = null; try{ res = JSON.parse(raw); } catch(e){ res = { ok: false, error: raw }; }
              if (!res.ok) { console.warn('Failed to load folder content', res.error || raw); return; }
              // Insert folders
              if (res.folders && res.folders.length) {
                res.folders.forEach(f => {
                  const created = createFolderRow(f.name, wrapper.dataset.canEdit && wrapper.dataset.canEdit !== '0');
                  created.row.dataset.folderPath = f.path;
                  created.row.dataset.folderName = f.name;
                  // TBD: folder meta or download/delete buttons handled by ensureFolderPath
                  children.appendChild(created.row);
                  children.appendChild(created.children);
                });
              }
              // Insert files
              if (res.files && res.files.length) {
                res.files.forEach(a => {
                  const fileItem = buildItem(a, { canEdit: wrapper.dataset.canEdit && wrapper.dataset.canEdit !== '0' });
                  children.appendChild(fileItem);
                });
              }
              children.dataset.loaded = '1';
            }).catch(err => { console.warn('list_folder failed', err); });
          }
        }
        row.classList.remove('collapsed');
        children.classList.remove('d-none');
        if (caret && window.LL_ICON_URLS && window.LL_ICON_URLS.caret_down) {
          caret.src = window.LL_ICON_URLS.caret_down;
        }
      } else {
        row.classList.add('collapsed');
        children.classList.add('d-none');
        if (caret && window.LL_ICON_URLS && window.LL_ICON_URLS.caret_right) {
          caret.src = window.LL_ICON_URLS.caret_right;
        }
      }
    });
    // 评论交互：回复表单显示/隐藏 与 展开/收起直接回复列表
    document.addEventListener('click', (e) => {
      const replyBtn = e.target.closest('.btn-reply');
      if (replyBtn) {
        const item = replyBtn.closest('.comment-item');
        if (!item) return;
        const form = item.querySelector('.reply-form');
        if (!form) return;
        form.classList.toggle('d-none');
        const textarea = form.querySelector('textarea');
        if (textarea && !form.classList.contains('d-none')) textarea.focus();
        return;
      }
      const toggle = e.target.closest('.btn-toggle-replies');
      if (toggle) {
        const target = document.querySelector(toggle.dataset.target);
        if (!target) return;
        const count = target.querySelectorAll('.list-group-item').length || 0;
        // 新的展开/收起逻辑基于 CSS 的 .replies-container.expanded 动画
        const isExpanded = target.classList.contains('expanded');
        if (!isExpanded) {
          target.classList.add('expanded');
          toggle.textContent = `收起回复 (${count})`;
          toggle.setAttribute('aria-expanded', 'true');
        } else {
          target.classList.remove('expanded');
          toggle.textContent = `展开回复 (${count})`;
          toggle.setAttribute('aria-expanded', 'false');
        }
        return;
      }
    });

    // 支持评论表单中的文件夹相对路径：为每个 input[name=comment_attachments] 添加 hidden relative_path[index]
    document.querySelectorAll('input[type=file][name="comment_attachments"]').forEach((input)=>{
      input.addEventListener('change', (e)=>{
        const files = Array.from(input.files || []);
        const form = input.closest('form');
        if(!form) return;
        // 清理旧的 relative_path[*]
        Array.from(form.querySelectorAll('input[name^="relative_path["]')).forEach(el=>el.remove());
        files.forEach((f, idx)=>{
          const rel = f.webkitRelativePath || f.relativePath || '';
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = `relative_path[${idx}]`;
          hidden.value = rel;
          form.appendChild(hidden);
        });
      });
    });
  });
  // Expose uploadBatch for other scripts (e.g., pre-submit auto-async on forms)
  window.LL_uploadBatch = uploadBatch;
})();
