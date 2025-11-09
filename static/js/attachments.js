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
    link.href = a.url;
    link.target = '_blank';
    link.className = 'flex-grow-1 text-decoration-none text-body';
    link.textContent = a.name;
    item.appendChild(link);

    const sizeSpan = document.createElement('span');
    sizeSpan.className = 'text-muted small me-3';
    sizeSpan.textContent = humanSize(a.size);
    item.appendChild(sizeSpan);

    // Delete button needs owner info, which we don't have here.
    // It will be added if the current user is the owner.
    // For now, we can add a placeholder or handle it differently.
    // Let's assume the delete button is only for owners and added dynamically
    // based on user permissions known at render time.
    // The button is now part of the initial HTML, so we just need to handle its click.
    // When adding dynamically, we need to know if the current user is the owner.
    // Let's simplify: the delete button will be handled by the global click handler
    // if it exists in the initial HTML. For dynamically added items, we'll omit it
    // as we can't securely determine ownership on the client side without more info.
    // A better approach would be to have the server response for upload include owner info
    // and compare with a global JS variable `currentUserId`.
    // For now, let's just build the item without the delete button.
    // The user can refresh to see the delete button if they are the owner.

    return item;
  }

  async function uploadBatch(wrapper, files){
    const parentType=wrapper.dataset.parentType;
    const parentId=wrapper.dataset.parentId;
    if(!files.length) return;
    
    // Find the container for attachment items. It might be the wrapper itself
    // or a specific list inside it. Let's make it flexible.
    // The new structure uses the wrapper directly as the container for items.
  const listContainer = wrapper;

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
      // 简化处理：将新文件追加到容器（树状视图下一次刷新会重建层级）
      data.files.forEach(f=>{ 
        const newItem = buildItem(f);
        // Find where to insert the new item. It should be before the upload input.
        const inputContainer = wrapper.querySelector('.mt-2');
        if (inputContainer) {
          listContainer.insertBefore(newItem, inputContainer);
        } else {
          listContainer.appendChild(newItem);
        }
      });
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
      const item = btn.closest('.ll-attachment-item');
      if(item) item.remove();
    }catch(err){
      alert('删除失败: '+err.message);
    }finally{ btn.disabled=false; }
  }

  function enhanceWrapper(wrapper){
    const inputs = wrapper.querySelectorAll('input[type=file]');
    if(!inputs || !inputs.length) return;
    inputs.forEach((input)=>{
      input.addEventListener('change', (e)=>{
        const files = e.target.files;
        if(files && files.length){
          uploadBatch(wrapper, files);
          input.value=''; // reset
        }
      });
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
      const btn = e.target.closest('.delete-attachment');
      if(btn){
        const id = btn.dataset.id; if(id) deleteItem(id, btn);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('.ll-attachments').forEach(enhanceWrapper);
    bindGlobalClicks();
    // 目录展开/折叠逻辑（GitHub 风格）
    document.addEventListener('click', (e) => {
      const row = e.target.closest('.ll-folder-row');
      if (!row) return;
      const children = row.nextElementSibling;
      if (!children || !children.classList.contains('ll-folder-children')) return;
      const caret = row.querySelector('.ll-caret-icon');
      const collapsed = row.classList.contains('collapsed');
      if (collapsed) {
        row.classList.remove('collapsed');
        children.classList.remove('d-none');
        if (caret && window.LL_ICON_URLS) caret.src = window.LL_ICON_URLS.caret_down;
      } else {
        row.classList.add('collapsed');
        children.classList.add('d-none');
        if (caret && window.LL_ICON_URLS) caret.src = window.LL_ICON_URLS.caret_right;
      }
    });
  });
})();
