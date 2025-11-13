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
  // 文件名链接改为指向预览端点，预览页面负责高亮与下载操作；下载按钮仍走专用端点
  link.href = `/attachments/preview/${a.id}/`;
    link.target = '_self';
    link.className = 'flex-grow-1 text-decoration-none text-body';
    link.textContent = a.name;
    item.appendChild(link);

  const sizeSpan = document.createElement('span');
  sizeSpan.className = 'text-muted small me-3';
  sizeSpan.textContent = humanSize(a.size);
  item.appendChild(sizeSpan);
  // 下载按钮（outline 绿色）
  const dl = document.createElement('a');
  dl.className='btn btn-sm btn-outline-success me-2';
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

  // For wrappers that opt-out of async upload (data-async-upload="0"),
  // render a staged preview of the selected files/folders in the UI
  // without sending them to server. This mirrors the tree-building logic
  // used after async upload so users see folder structure immediately.
  function stageFiles(wrapper, files){
    if(!files || !files.length) return;
    const listContainer = wrapper.querySelector('.ll-attach-list') || wrapper;
    // Ensure hidden relative_path inputs exist on the enclosing form
    const form = wrapper.closest('form');
    // Build items and insert into appropriate folder containers
    Array.from(files).forEach((f, i)=>{
      const rel = f.webkitRelativePath || f.relativePath || f.name || '';
      // create a simple representation object similar to server response
      const obj = { id: `staged-${Date.now()}-${i}`, name: f.name, size: f.size || 0, relative_path: rel, is_image: false, is_text: false, is_audio: false, is_video: false };
      const newItem = buildItem(obj);
      // staged items should not link to preview endpoint (no server id yet)
      if(String(obj.id).startsWith('staged-')){
        const a = newItem.querySelector('a');
        if(a){ a.href = 'javascript:void(0)'; a.classList.add('staged-link'); }
      }
      newItem.classList.add('staged-attachment-item');
      // ensure folder containers exist
      let targetContainer = listContainer;
      if (obj.relative_path && obj.relative_path.includes('/')){
        targetContainer = ensureFolderPath(listContainer, obj.relative_path) || listContainer;
      }
      const inputContainer = (targetContainer === listContainer) ? listContainer.querySelector('.mt-2') : null;
      if (inputContainer) {
        targetContainer.insertBefore(newItem, inputContainer);
      } else {
        targetContainer.appendChild(newItem);
      }
      // Do NOT add hidden inputs here; the page-level script is responsible
      // for building numeric relative_path[...] inputs so indices match
      // request.FILES ordering when the form is submitted.
    });
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
          const asyncAttr = wrapper.dataset.asyncUpload;
          if(asyncAttr === '0'){
            // staged mode: render preview locally instead of uploading
            stageFiles(wrapper, files);
            // do not clear input.value to allow form submission to include files
          } else {
            uploadBatch(wrapper, files);
            // clear input after async upload to allow re-selecting same files
            input.value=''; // reset
          }
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
      // 附件删除（模板 class: ll-attach-del）
      const attDel = e.target.closest('.ll-attach-del') || e.target.closest('.delete-attachment');
      if(attDel){
        const id = attDel.dataset.id;
        // If this attachment sits inside a wrapper that opted out of async
        // uploads (data-async-upload="0"), stage the deletion locally and
        // only perform actual delete when the enclosing form is submitted.
        const wrapper = attDel.closest('.ll-attachments');
        const asyncAttr = wrapper?.dataset?.asyncUpload;
        if(asyncAttr === '0'){
          // toggle staged delete state on the attachment item
          const item = attDel.closest('.ll-attachment-item');
          if(!item) return;
          const form = item.closest('form') || document.querySelector('form');
          if(!form){
            alert('无法找到表单以暂存删除操作');
            return;
          }
          const hiddenName = 'pending_delete_attachment_ids';
          const existing = form.querySelector(`input[name="${hiddenName}"][value="${id}"]`);
          if(existing){
            // 已标记为删除 -> 取消标记
            existing.remove();
            item.classList.remove('pending-delete');
            attDel.textContent = '删除';
          } else {
            const hid = document.createElement('input'); hid.type='hidden'; hid.name=hiddenName; hid.value=id; form.appendChild(hid);
            item.classList.add('pending-delete');
            attDel.textContent = '取消删除';
          }
          return;
        }
        if(id) deleteItem(id, attDel);
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
        headers: {'X-CSRFToken': csrftoken, 'X-Requested-With': 'XMLHttpRequest'}
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
    // Only enhance wrappers that allow async upload. To stage attachments and
    // only persist them on final form submit (new/edit pages), set
    // data-async-upload="0" on the .ll-attachments container. By default
    // enhancement remains enabled for pages that expect immediate async
    // upload (discovery, comment upload UI, etc.).
    // Enhance all wrappers; enhanceWrapper internally checks wrapper.dataset.asyncUpload
    // and will either perform async uploads or stage files locally depending on that flag.
    document.querySelectorAll('.ll-attachments').forEach((el)=>{
      enhanceWrapper(el);
    });
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
})();
