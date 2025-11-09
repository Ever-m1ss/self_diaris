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
  // 统一通过后端下载端点，避免直接走媒体 URL 引发 404 或缺少下载头
  link.href = `/attachments/download/${a.id}/`;
    link.target = '_blank';
    link.className = 'flex-grow-1 text-decoration-none text-body';
    link.textContent = a.name;
    item.appendChild(link);

  const sizeSpan = document.createElement('span');
  sizeSpan.className = 'text-muted small me-3';
  sizeSpan.textContent = humanSize(a.size);
  item.appendChild(sizeSpan);
  // 下载按钮
  const dl = document.createElement('a');
  dl.className='btn btn-sm btn-outline-secondary me-2';
  dl.textContent='下载';
  dl.href='/attachments/download/'+a.id+'/';
  item.appendChild(dl);

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
  // 优先使用统一的包裹容器（保证所有条目外框一致）
  const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;

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
      // 动态将文件插入对应的文件夹层级（无需刷新）
      data.files.forEach(f=>{
        const newItem = buildItem(f);
        let targetContainer = listContainer;
        if (f.relative_path && f.relative_path.includes('/')) {
          // ensureFolderPath 期望传入包含文件名的完整路径，它内部会去掉最后一段作为文件夹链
          targetContainer = ensureFolderPath(listContainer, f.relative_path) || listContainer;
        }
        // 如果目标是顶层并存在输入容器，则插入到输入容器之前；否则直接 append
        const inputContainer = (targetContainer === listContainer) ? listContainer.querySelector('.mt-2') : null;
        if (inputContainer) {
          targetContainer.insertBefore(newItem, inputContainer);
        } else {
          targetContainer.appendChild(newItem);
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
    try {
      const resp = await fetch(`/attachments/delete/${id}/`, {
        method: 'POST',
        headers: {'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest'}
      });
      if(!resp.ok){
        throw new Error(await resp.text() || resp.status);
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
  function createFolderRow(name){
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
    const canEdit = row.closest('.ll-attachments')?.dataset.canEdit;
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
        const created=createFolderRow(name);
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
        const delBtn = created.row.querySelector('.ll-folder-del');
        if(delBtn){ delBtn.dataset.folderPath = accumulated; }
        // 保持新建文件夹默认折叠，不展开
        container=created.children;
      }else{
        accumulated = accumulated ? (accumulated + '/' + name) : name;
        foundRow.dataset.folderPath = accumulated;
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
          headers:{'X-CSRFToken': csrftoken,'X-Requested-With':'XMLHttpRequest'},
          body: fd
        }).then(r=>r.json()).then(res=>{
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
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('.ll-attachments').forEach(enhanceWrapper);
    bindGlobalClicks();
    // 目录展开/折叠逻辑（GitHub 风格）
    document.addEventListener('click', (e) => {
      const row = e.target.closest('.ll-folder-row');
      if (!row) return;
      // 如果点击的是操作按钮（删除/下载）不要触发折叠
      if (e.target.closest('.ll-folder-del') || e.target.closest('.ll-folder-dl')) return;
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
