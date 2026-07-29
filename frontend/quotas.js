document.addEventListener("DOMContentLoaded", () => {
    const token = localStorage.getItem('token');
    if (!token) {
        window.location.href = '/login';
        return;
    }
    loadQuotas();
});

async function fetchWithAuth(url, options = {}) {
    const token = localStorage.getItem('token');
    const headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
    };

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401 || response.status === 403) {
        localStorage.removeItem('token');
        localStorage.removeItem('role');
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }
    return response;
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    window.location.href = '/login';
}
const DEFAULT_CATEGORIES = {
    "Género": ["Hombre", "Mujer"],
    "Región": ["Norte", "Centro", "Sur"],
    "Edad": ["18-30", "31-45", "46+"],
    "NSE": ["MT", "MB", "BA"],
    "Tipo de Punto": ["Centro Comercial", "Iglesia", "Parque", "Plaza/Plazoleta", "Zona Comercial", "Colegio/Universidad"]
};

const PRIORITY_ORDER = ["Tipo de Punto", "Género", "Región", "Edad", "NSE"];
const cartesian = (...a) => a.reduce((acc, b) => acc.flatMap(d => b.map(e => [d, e].flat())));

async function loadQuotas() {
    try {
        const res = await fetchWithAuth('/api/quotas');
        if (!res.ok) return;

        const data = await res.json();
        const container = document.getElementById('studiesContainer');
        container.innerHTML = '';

        if (Object.keys(data).length === 0) {
            container.innerHTML = '<p style="text-align:center; font-weight:600; color: var(--text-muted); margin-top:3rem;">No hay estudios configurados aún.</p>';
            return;
        }

        const showClosed = document.getElementById('showClosedStudies') ? document.getElementById('showClosedStudies').checked : false;

        for (const [studyCode, quotas] of Object.entries(data)) {
            if (quotas.length === 0) continue;
            
            const studyId = quotas[0].study_id;
            const isClosed = quotas[0].is_closed === 1;
            if (isClosed && !showClosed) continue;
            
            const stdRoot = {};
            const ptRoot = {};
            const exactaQuotas = [];

            quotas.forEach(q => {
                if (q.value && q.value.startsWith("Censos")) return;
                
                if (q.category === "Exacta") {
                    exactaQuotas.push(q);
                } else if (q.category === "Tipo de Punto") {
                    if (q.value && q.value.includes(" | ")) {
                        exactaQuotas.push(q);
                    } else {
                        if (!ptRoot["Tipo de Punto"]) ptRoot["Tipo de Punto"] = { __isLeaf: true, __quotas: [] };
                        ptRoot["Tipo de Punto"].__quotas.push(q);
                    }
                } else {
                    const parts = q.category === "General" ? [] : q.category.split(" | ");
                    let current = stdRoot;
                    parts.forEach((p, idx) => {
                        if (!current[p]) {
                            current[p] = (idx === parts.length - 1) ? { __isLeaf: true, __quotas: [] } : {};
                        }
                        current = current[p];
                    });
                    if (parts.length === 0) {
                        if (!current['Total']) current['Total'] = { __isLeaf: true, __quotas: [] };
                        current['Total'].__quotas.push(q);
                    } else {
                        current.__quotas.push(q);
                    }
                }
            });

            enrichWithTotals(stdRoot);
            
            const stdHtml = renderTreeHtml(stdRoot, true);
            const exactaHtml = exactaQuotas.length > 0 ? renderExactaGridHtml(exactaQuotas) : "";
            const ptHtml = Object.keys(ptRoot).length > 0 ? renderTreeHtml(ptRoot, true) : "";

            const statusBadge = isClosed ? '<span style="background:var(--text-muted); color:white; padding:2px 8px; border-radius:10px; margin-left:10px; font-size:0.8rem;"><i class="fas fa-archive"></i> Cerrado</span>' : '';
            const lockIcon = isClosed ? 'fa-lock-open' : 'fa-lock';
            const lockColor = isClosed ? '#10b981' : '#64748b';
            const lockTitle = isClosed ? 'Reabrir Estudio' : 'Cerrar Estudio (Ocultar del bot)';

            const studyWrapper = document.createElement('div');
            studyWrapper.className = 'htable-container';
            studyWrapper.style.marginBottom = "2.5rem";
            studyWrapper.innerHTML = `
                <div class="study-label" style="${isClosed ? 'background: #94a3b8;' : ''}">
                    <span>ESTUDIO: ${studyCode} ${statusBadge} <span style="font-size:0.8rem; background:rgba(255,255,255,0.2); color:white; padding:2px 8px; border-radius:10px; margin-left:10px;">ID: ${studyId || 'N/A'} | ${quotas.length} ítems</span></span>
                    <div style="display:flex; gap: 8px;">
                        <button onclick="toggleStudyStatus('${studyId}', '${studyCode}')" style="background:${lockColor}; color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="${lockTitle}"><i class="fas ${lockIcon}"></i></button>
                        <button onclick="exportStudyData('${studyId}', '${studyCode}')" style="background:#16a34a; color:white; border:none; padding:4px 12px; border-radius:6px; cursor:pointer; font-weight:bold; display:flex; align-items:center; gap:5px;" title="Descargar Reporte Excel">
                           <i class="fas fa-file-excel"></i> <span>Reporte</span>
                        </button>
                        <button onclick="editStudy('${studyId}', '${studyCode}')" style="background:var(--warning); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Editar Estudio"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteStudyGlobal('${studyId}', '${studyCode}')" style="background:var(--danger); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Eliminar Estudio"><i class="fas fa-trash-alt"></i></button>
                    </div>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 20px; padding: 15px; background: #fff; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; ${isClosed ? 'opacity:0.6; pointer-events:none;' : ''}">
                    ${exactaHtml || ptHtml ? `
                    <div style="flex: 1 1 300px; min-width: 300px;">
                        <h4 style="color:var(--primary); margin-bottom:0.8rem; font-size:1rem;"><i class="fas fa-map-marker-alt"></i> Cuota de Tipos de Puntos</h4>
                        <div class="htable-root-groups" style="border:1px solid #e2e8f0; border-radius:8px; overflow:hidden;">${exactaHtml}${ptHtml}</div>
                    </div>` : ""}
                    
                    <div style="flex: 2 1 600px; min-width: 400px;">
                        <h4 style="color:var(--primary); margin-bottom:0.8rem; font-size:1rem;"><i class="fas fa-users"></i> Cuota Cuadro Demográfico</h4>
                        <div class="htable-root-groups" style="border:1px solid #e2e8f0; border-radius:8px; overflow:hidden;">${stdHtml}</div>
                    </div>
                </div>
            `;
            container.appendChild(studyWrapper);
        }
    } catch (e) {
        console.error(e);
    }
}

function renderTreeHtml(node, isRoot = false, level = 0, isProposal = false) {
    if (node.__isLeaf) {
        const cols = node.__quotas;

        let headerHtml = '';
        let bodyHtml = '';
        cols.forEach(q => {
            const isTotal = q.is_total || false;
            headerHtml += `<div class="${isTotal ? 'is-total-header' : ''}">${isProposal ? q.val : q.value}</div>`;
            if (isProposal) {
                bodyHtml += `
                    <div>
                        <input type="number" class="htable-input" value="${q.target}" data-cat="${q.dbCat}" data-val="${q.val}" data-point="${q.point || 'General'}" min="0">
                    </div>
                `;
            } else {
                const percent = q.target_count > 0 ? Math.min(100, Math.round((q.current_count / q.target_count) * 100)) : 0;
                let color = '#ef4444';
                if (percent >= 100) color = '#3b82f6';
                else if (percent >= 80) color = '#22c55e';
                else if (percent >= 50) color = '#f59e0b';

                bodyHtml += `
                    <div class="${isTotal ? 'is-total-cell' : ''}">
                        <div class="val-container">
                            <div class="val-disp">${q.current_count}</div>
                            <div class="val-target">/ ${q.target_count}</div>
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width:${percent}%; background:${color};"></div>
                        </div>
                    </div>
                `;
            }
        });

        return `
            <div class="htable-cols-container">
                <div class="htable-cols-row header-row">${headerHtml}</div>
                <div class="htable-cols-row body-row">${bodyHtml}</div>
            </div>
        `;
    }

    let html = '';
    for (const key of Object.keys(node)) {
        if (key === '__isLeaf' || key === '__quotas') continue;

        const childHtml = renderTreeHtml(node[key], false, level + 1, isProposal);

        html += `<div class="htable-group">`;
        if (key !== 'Total' || level > 0) {
            html += `<div class="htable-group-header level-${level}-header">${key}</div>`;
        }
        html += childHtml;
        html += `</div>`;
    }
    return html;
}

function enrichWithTotals(node) {
    if (node.__isLeaf) {
        // Horizontal Total (A la derecha)
        const totalCurr = node.__quotas.reduce((sum, q) => sum + (q.current_count || 0), 0);
        const totalTarg = node.__quotas.reduce((sum, q) => sum + (q.target_count || 0), 0);
        node.__quotas.push({
            value: 'Total',
            current_count: totalCurr,
            target_count: totalTarg,
            is_total: true
        });
        // Return summary for parent summation
        const byVal = {};
        node.__quotas.forEach(q => {
            if (q.value !== 'Total') {
                byVal[q.value] = { c: q.current_count, t: q.target_count };
            }
        });
        return { current: totalCurr, target: totalTarg, countsByVal: byVal };
    }

    const keys = Object.keys(node).filter(k => k !== '__isLeaf' && k !== '__quotas');
    if (keys.length === 0) return { current: 0, target: 0 };

    let totalCurr = 0;
    let totalTarg = 0;
    let aggregateCols = {};

    keys.forEach(k => {
        const res = enrichWithTotals(node[k]);
        totalCurr += res.current;
        totalTarg += res.target;
        if (res.countsByVal) {
            for (const [v, counts] of Object.entries(res.countsByVal)) {
                if (!aggregateCols[v]) aggregateCols[v] = { c: 0, t: 0 };
                aggregateCols[v].c += counts.c;
                aggregateCols[v].t += counts.t;
            }
        }
    });

    // Vertical Total (Para abajo)
    if (Object.keys(aggregateCols).length > 0) {
        const totalQuotas = [];
        // Maintain column order if possible - here we just use whatever keys were in aggregateCols
        for (const [v, counts] of Object.entries(aggregateCols)) {
            totalQuotas.push({ value: v, current_count: counts.c, target_count: counts.t, is_total: true });
        }
        // Grand total for this group
        totalQuotas.push({ value: 'Total', current_count: totalCurr, target_count: totalTarg, is_total: true });
        
        node['Total'] = { __isLeaf: true, __quotas: totalQuotas };
    }

    return { current: totalCurr, target: totalTarg };
}

function toggleAgeInputs() {
    const isChecked = document.getElementById('chkEdad').checked;
    document.getElementById('dynamicAgeContainer').style.display = isChecked ? 'block' : 'none';
    generateProposals();
}

function addAgeRange() {
    const list = document.getElementById('ageInputsList');
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'age-input-field';
    input.placeholder = 'Nuevo';
    input.style = 'width:100px; padding:6px; border:1px solid #ccc; border-radius:5px; text-align:center; font-weight:600;';
    input.oninput = generateProposals;
    list.appendChild(input);
    generateProposals();
}

function togglePointTypeInputs() {
    const isChecked = document.getElementById('chkPointType').checked;
    const container = document.getElementById('dynamicPointTypeContainer');
    if (container) container.style.display = isChecked ? 'block' : 'none';
    generateProposals();
}

function createPointTypeInput(val) {
    const wrapper = document.createElement('div');
    wrapper.style = 'position:relative; display:inline-block; margin-right:5px;';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'point-type-input-field';
    input.value = val;
    input.placeholder = val ? "" : "Punto X"; // Use placeholder if empty
    input.style = 'width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:var(--text-main); padding-right:28px; background:white;';
    input.oninput = generateProposals;
    
    const deleteBtn = document.createElement('span');
    deleteBtn.innerHTML = '&times;';
    deleteBtn.title = 'Eliminar este punto';
    deleteBtn.style = 'position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1; transition: opacity 0.2s;';
    deleteBtn.onmouseover = () => deleteBtn.style.opacity = '0.7';
    deleteBtn.onmouseout = () => deleteBtn.style.opacity = '1';
    deleteBtn.onclick = () => {
        wrapper.remove();
        generateProposals();
    };
    
    wrapper.appendChild(input);
    wrapper.appendChild(deleteBtn);
    return wrapper;
}

function addPointTypeItem() {
    const list = document.getElementById('pointTypeInputsList');
    if (list) {
        list.appendChild(createPointTypeInput(''));
    }
}

function generateProposals() {
    const total = parseInt(document.getElementById('totalSurveys').value, 10) || 0;
    let checkboxes = Array.from(document.querySelectorAll('.category-toggles input[type="checkbox"]:checked')).map(cb => cb.value);

    checkboxes.sort((a, b) => PRIORITY_ORDER.indexOf(a) - PRIORITY_ORDER.indexOf(b));
    const container = document.getElementById('proposalsContainer');
    container.innerHTML = '';

    if (total <= 0) return;

    let hasPointType = checkboxes.includes("Tipo de Punto");
    if (hasPointType) {
        const ptInputs = Array.from(document.querySelectorAll('.point-type-input-field')).map(i => i.value.trim()).filter(v => v !== "");
        const pointTypesToUse = ptInputs; // Only use what is in the inputs
        
        if (pointTypesToUse.length === 0) {
             container.innerHTML += `
                <div style="margin-bottom: 2rem; border: 2px dashed #bae6fd; padding:1.5rem; border-radius:12px; text-align:center; color:#0369a1;">
                    <i class="fas fa-info-circle"></i> No hay tipos de puntos definidos arriba.
                </div>
             `;
        } else {
        
        const ptRoot = {};
        ptRoot["Tipo de Punto"] = { __isLeaf: true, __quotas: [] };
        
        // Distribute total across point types for suggestion
        const ptBaseTarget = Math.floor(total / pointTypesToUse.length);
        let ptRemainder = total % pointTypesToUse.length;

        pointTypesToUse.forEach(pt => {
            let target = ptBaseTarget;
            if (ptRemainder > 0) { target += 1; ptRemainder -= 1; }
            ptRoot["Tipo de Punto"].__quotas.push({
                val: pt,
                target: target,
                dbCat: "Tipo de Punto",
                point: pt
            });
        });
        
        const ptHtml = renderTreeHtml(ptRoot, true, 0, true);
        container.innerHTML += `
            <div style="margin-bottom: 2rem;">
                <h4 style="color:var(--primary); margin-bottom:0.5rem;"><i class="fas fa-map-marker-alt"></i> Cuota de Tipos de Puntos</h4>
                <div class="htable-container" style="border-width:1px;"><div class="htable-root-groups">${ptHtml}</div></div>
            </div>
        `;
        }
    }

    // 2. Standard Quotas
    let standardCheckboxes = checkboxes.filter(c => c !== "Tipo de Punto");

    if (standardCheckboxes.length === 0) {
        container.innerHTML += `
        <div style="margin-bottom: 1rem;">
            <h4 style="color:var(--primary); margin-bottom:0.5rem;"><i class="fas fa-users"></i> Cuota Demográfica General</h4>
            <div class="htable-container" style="border-width:1px;">
                <div class="htable-cols-container">
                    <div class="htable-cols-row header-row"><div>Total General</div></div>
                    <div class="htable-cols-row body-row">
                        <div><input type="number" class="htable-input" value="${total}" data-cat="General" data-val="Total" min="1"></div>
                    </div>
                </div>
            </div>
        </div>`;
        return;
    }

    const minorCat = standardCheckboxes[standardCheckboxes.length - 1];
    const majorCats = standardCheckboxes.slice(0, standardCheckboxes.length - 1);

    let minorArrays = [];
    if (minorCat === "Edad") {
        const ageInputs = Array.from(document.querySelectorAll('.age-input-field')).map(i => i.value.trim()).filter(v => v !== "");
        minorArrays = ageInputs.length > 0 ? ageInputs : ["Total"];
    } else {
        minorArrays = DEFAULT_CATEGORIES[minorCat];
        if (!minorArrays || minorArrays.length === 0) minorArrays = ["Total"];
    }

    let majorCombos = [["Total"]];
    if (majorCats.length > 0) {
        const majorArrays = majorCats.map(cat => {
            if (cat === "Edad") {
                const ageInputs = Array.from(document.querySelectorAll('.age-input-field')).map(i => i.value.trim()).filter(v => v !== "");
                return ageInputs.length > 0 ? ageInputs : ["Total"];
            }
            return DEFAULT_CATEGORIES[cat] || ["Total"];
        });
        majorCombos = cartesian(...majorArrays);
    }

    const itemsPerGroup = minorArrays.length;
    const totalGroups = majorCombos.length;
    const totalItems = totalGroups * itemsPerGroup;

    const baseTarget = Math.floor(total / totalItems);
    let remainder = total % totalItems;

    const root = {};
    majorCombos.forEach(majorCombo => {
        const majorComboArray = Array.isArray(majorCombo) ? majorCombo : [majorCombo];
        const dbCategory = majorCats.length > 0 ? majorComboArray.join(" | ") : minorCat;

        let current = root;
        if (majorCats.length > 0) {
            majorComboArray.forEach((p, idx) => {
                const nodeName = p;
                if (!current[nodeName]) {
                    current[nodeName] = (idx === majorComboArray.length - 1) ? { __isLeaf: true, __quotas: [] } : {};
                }
                current = current[nodeName];
            });
        } else {
            if (!current[minorCat]) current[minorCat] = { __isLeaf: true, __quotas: [] };
            current = current[minorCat];
        }

        minorArrays.forEach(minorVal => {
            let target = baseTarget;
            if (remainder > 0) { target += 1; remainder -= 1; }

            current.__quotas.push({
                val: minorVal,
                target: target,
                dbCat: dbCategory,
                point: "General"
            });
        });
    });

    const html = renderTreeHtml(root, true, 0, true);
    container.innerHTML += `
        <div>
            <h4 style="color:var(--primary); margin-bottom:0.5rem;"><i class="fas fa-users"></i> Cuota Cuadro Demográfico</h4>
            <div class="htable-container" style="border-width:1px; margin-bottom:0;"><div class="htable-root-groups">${html}</div></div>
        </div>
    `;
}

function openModal() {
    document.getElementById('quotaModal').style.display = 'flex';
    document.getElementById('studyCode').value = '';
    document.getElementById('totalSurveys').value = '';
    document.getElementById('studyCode').readOnly = false;
    
    const idHidden = document.getElementById('studyIdHidden');
    if (idHidden) idHidden.value = '';

    document.querySelectorAll('.category-toggles input[type="checkbox"]').forEach(cb => cb.checked = false);

    const ptContainer = document.getElementById('dynamicPointTypeContainer');
    if (ptContainer) {
        ptContainer.style.display = 'none';
        const list = document.getElementById('pointTypeInputsList');
        if (list) {
            list.innerHTML = `
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Centro Comercial" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Iglesia" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Parque" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Plaza/Plazoleta" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Zona Comercial" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
                <div style="position:relative; display:inline-block; margin-right:5px;">
                    <input type="text" class="point-type-input-field" value="Colegio/Universidad" style="width:145px; padding:8px; border:1px solid #cbd5e1; border-radius:10px; text-align:center; font-weight:700; color:#1e293b; padding-right:28px; background:white;" oninput="generateProposals()">
                    <span title="Eliminar este punto" style="position:absolute; right:8px; top:50%; transform:translateY(-50%); cursor:pointer; color:#ef4444; font-size:1.4rem; font-weight:bold; line-height:1;" onclick="this.parentElement.remove(); generateProposals();">&times;</span>
                </div>
            `;
        }
    }

    document.getElementById('proposalsContainer').innerHTML = '';
    // Trigger a refresh of the grids
    generateProposals();
}

function closeModal() { document.getElementById('quotaModal').style.display = 'none'; }

async function saveBatchQuotas() {
    const studyCode = document.getElementById('studyCode').value.trim();
    if (!studyCode) { alert("Ingresa el ID del estudio"); return; }

    const studyId = document.getElementById('studyIdHidden').value;

    const payload = [];
    document.querySelectorAll('.htable-input').forEach(input => {
        const cat = input.getAttribute('data-cat');
        const val = input.getAttribute('data-val');
        const rowPoint = input.getAttribute('data-point') || 'General';
        const target = parseInt(input.value, 10);
        if (target >= 0) {
            payload.push({ 
                study_id: studyId ? parseInt(studyId, 10) : null,
                study_code: studyCode, 
                category: cat, 
                value: val, 
                target_count: target, 
                point_type: rowPoint 
            });
        }
    });

    if (payload.length === 0) return;

    try {
        const res = await fetchWithAuth('/api/quotas/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) { closeModal(); loadQuotas(); }
    } catch (e) { console.error(e); }
}

async function deleteStudyGlobal(studyId, studyName) {
    if (!confirm(`¿Estás completamente seguro de ELIMINAR todo el estudio ${studyName}?`)) return;
    try {
        const res = await fetchWithAuth(`/api/quotas/study/${encodeURIComponent(studyName)}`, { method: 'DELETE' });
        if (res.ok) loadQuotas();
        else alert("Error al eliminar el estudio");
    } catch (e) {
        console.error(e);
        alert("Error de conexión al intentar eliminar el estudio");
    }
}

function editStudy(studyId, studyCode) {
    if (!studyCode) return;
    console.log("Editando estudio ID:", studyId, "Nombre:", studyCode);
    
    if (confirm("¿Quieres editar los objetivos de cuota para el estudio " + studyCode + "?")) {
        // Preferimos el study_id para la consulta si está disponible
        const url = studyId && studyId !== 'undefined' ? 
                    '/api/quotas?study_id=' + studyId : 
                    '/api/quotas?study_code=' + encodeURIComponent(studyCode);
        
        fetchWithAuth(url)
            .then(async res => {
                if (!res.ok) {
                    const errText = await res.text();
                    throw new Error(`Servidor respondió con status ${res.status}: ${errText}`);
                }
                return res.json();
            })
            .then(data => {
                console.log("Datos para edición recibidos:", data);
                
                // Buscamos las cuotas. Manejamos tanto data[studyCode] como data si viene plano.
                let quotasArr = data[studyCode];
                if (!quotasArr || quotasArr.length === 0) {
                    // Si no está bajo la clave del nombre, quizás es el primer elemento del objeto
                    const keys = Object.keys(data);
                    if (keys.length > 0) quotasArr = data[keys[0]];
                }

                if (!quotasArr || quotasArr.length === 0) {
                    alert("No se encontraron registros de cuotas para el estudio: " + studyCode);
                    return;
                }

                openModal();

                const scInput = document.getElementById('studyCode');
                const totalSurveysInput = document.getElementById('totalSurveys');
                const idHidden = document.getElementById('studyIdHidden');
                
                if (scInput) scInput.value = studyCode;
                if (idHidden) idHidden.value = studyId || "";

                let inferredTotal = 0;
                const foundCats = new Set();
                const customAges = new Set();
                const customPoints = new Set();
                let hasPointType = false;

                // Identificamos la primera categoría para sumar el total sin duplicar por dimensiones cruzadas
                const firstStandardCat = quotasArr.find(q => q.category !== "Tipo de Punto" && q.category !== "General")?.category || "General";
                
                quotasArr.forEach(q => {
                    if (q.category === "Tipo de Punto") {
                        hasPointType = true;
                        if (q.value) customPoints.add(q.value);
                    } else {
                        // Total
                        if (q.category === firstStandardCat) {
                            inferredTotal += (q.target_count || 0);
                        }

                        // Categorías (Demográficas) - Detección inteligente
                        const dims = ["Género", "Región", "Edad", "NSE"];
                        
                        // 1. Detección por nombre explícito
                        dims.forEach(d => {
                            if (q.category.includes(d)) foundCats.add(d);
                        });

                        // 2. Detección por patrones de contenido
                        // Patrón Edad: Tiene guion (20-35) o signo más (45+)
                        if (q.category.includes("-") || q.category.includes("+") || q.value.includes("-") || q.value.includes("+")) {
                            foundCats.add("Edad");
                            if (q.value.includes("-") || q.value.includes("+")) {
                                customAges.add(q.value);
                            } else {
                                const parts = q.category.split(" | ");
                                const agePart = parts.find(p => p.includes("-") || p.includes("+"));
                                if (agePart) {
                                    customAges.add(agePart);
                                } else {
                                    customAges.add(q.category);
                                }
                            }
                        }

                        // Patrón NSE: Valores estándar (MT, MB, BA)
                        const nseVals = ["MT", "MB", "BA"];
                        if (nseVals.some(v => q.category.includes(v)) || nseVals.includes(q.value)) {
                            foundCats.add("NSE");
                        }

                        // Patrón Género: Hombre/Mujer
                        const genderVals = ["Hombre", "Mujer"];
                        if (genderVals.some(v => q.category.includes(v)) || genderVals.includes(q.value)) {
                            foundCats.add("Género");
                        }
                    }
                });

                if (totalSurveysInput) totalSurveysInput.value = inferredTotal;

                // 3. Marcar Checkboxes
                document.querySelectorAll('.category-toggles input[type="checkbox"]').forEach(cb => {
                    if (foundCats.has(cb.value) || 
                        (cb.value === "Tipo de Punto" && hasPointType) ||
                        (cb.value === "Edad" && customAges.size > 0)) {
                        cb.checked = true;
                    }
                });

                // 4. Restaurar Edades Personalizadas
                if (foundCats.has("Edad") && customAges.size > 0) {
                    const ageList = document.getElementById('ageInputsList');
                    if (ageList) {
                        ageList.innerHTML = '';
                        customAges.forEach(age => {
                            const input = document.createElement('input');
                            input.type = 'text';
                            input.className = 'age-input-field';
                            input.value = age;
                            input.style = 'width:100px; padding:6px; border:1px solid #ccc; border-radius:5px; text-align:center; font-weight:600;';
                            input.oninput = generateProposals;
                            ageList.appendChild(input);
                        });
                    }
                }
                toggleAgeInputs();

                // 5. Restaurar Tipos de Puntos
                if (hasPointType && customPoints.size > 0) {
                    const ptList = document.getElementById('pointTypeInputsList');
                    if (ptList) {
                        ptList.innerHTML = '';
                        customPoints.forEach(pt => {
                            ptList.appendChild(createPointTypeInput(pt));
                        });
                    }
                }
                togglePointTypeInputs();

                // 6. Generar Estructura e Inyectar Valores Reales
                console.log("Generando tabla y restaurando valores...");
                generateProposals();

                // Crear mapa de valores reales para inyección rápida
                const quotaMap = {};
                quotasArr.forEach(q => {
                    const key = `${q.category}|${q.value}|${q.point_type || 'General'}`;
                    quotaMap[key] = q.target_count;
                });

                // Retraso para esperar a que DOM se construya
                setTimeout(() => {
                    let restoredCount = 0;
                    document.querySelectorAll('.htable-input').forEach(input => {
                        const cat = input.getAttribute('data-cat');
                        const val = input.getAttribute('data-val');
                        const point = input.getAttribute('data-point') || 'General';
                        const key = `${cat}|${val}|${point}`;
                        
                        if (quotaMap[key] !== undefined) {
                            input.value = quotaMap[key];
                            restoredCount++;
                        }
                    });
                    console.log(`Edición lista. Se restauraron ${restoredCount} valores.`);
                }, 300);

            })
            .catch(err => {
                console.error("Error detallado en editStudy:", err);
                alert("No se pudo cargar el estudio para editar.\nDetalle: " + err.message);
            });
    }
}

async function exportStudyData(studyId, studyName) {
    try {
        const response = await fetch(`/api/export-data/${encodeURIComponent(studyName)}`);
        if (!response.ok) throw new Error("Error al descargar");
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `data_${studyName}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
    } catch (e) {
        console.error(e);
        alert("Error al descargar los datos.");
    }
}

async function simulateWebhook() {
    const phone = document.getElementById('simPhone').value.trim();
    const msg = document.getElementById('simMsg').value.trim();
    const responseBox = document.getElementById('simResponse');

    if (!phone || !msg) {
        alert("Por favor ingresa un número de teléfono ficticio y un mensaje.");
        return;
    }

    responseBox.style.display = 'block';
    responseBox.innerText = "⏳ Simulando envío al bot de WhatsApp...";
    responseBox.style.color = 'var(--text-muted)';
    responseBox.style.borderColor = 'var(--border-color)';

    try {
        const res = await fetch('/api/bot/webhook-simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phone, message: msg })
        });

        const data = await res.json();
        
        // Mostrar respuesta de texto
        responseBox.innerText = (data.reply || "Sin respuesta.");
        responseBox.style.color = (data.reply && data.reply.includes('❌')) ? 'var(--danger)' : '#166534';
        responseBox.style.borderColor = (data.reply && data.reply.includes('❌')) ? 'var(--danger)' : '#22c55e';

        // Mostrar opciones interactivas si existen
        if (data.interactive) {
            const intData = data.interactive;
            let optHtml = '<div style="margin-top:10px; border-top:1px dashed #ccc; padding-top:10px; color:#475569; font-size:0.9rem;"><strong>Opciones recibidas:</strong><ul style="margin:5px 0; padding-left:20px;">';
            
            if (intData.type === 'list') {
                intData.action.sections.forEach(sec => {
                    sec.rows.forEach(row => {
                        optHtml += `<li style="margin-bottom:4px;">${row.id}. ${row.title}</li>`;
                    });
                });
            } else if (intData.type === 'button') {
                intData.action.buttons.forEach(btn => {
                    optHtml += `<li style="margin-bottom:4px;">${btn.reply.id}. ${btn.reply.title}</li>`;
                });
            }
            optHtml += '</ul><small>(Escribe el número de la opción arriba para responder)</small></div>';
            responseBox.innerHTML += optHtml;
        }

        loadQuotas();
    } catch (e) {
        console.error(e);
        responseBox.innerText = "Error: no se pudo simular el webhook.";
        responseBox.style.color = 'var(--danger)';
    }
}

async function toggleStudyStatus(studyId, studyName) {
    if (!confirm(`¿Deseas cambiar el estado (Abrir/Cerrar) del estudio ${studyName}?`)) return;
    try {
        const res = await fetchWithAuth(`/api/quotas/study/${studyId}/toggle-status`, { method: 'PUT' });
        if (res.ok) loadQuotas();
        else alert("Error al cambiar el estado del estudio");
    } catch (e) { 
        console.error(e); 
        alert("Error de conexión al intentar cambiar el estado");
    }
}

function openAgentsModal() {
    document.getElementById('agentsModal').style.display = 'flex';
    loadAgents();
}

function closeAgentsModal() {
    document.getElementById('agentsModal').style.display = 'none';
}

async function loadAgents() {
    const container = document.getElementById('agentsListContainer');
    container.innerHTML = '<p style="text-align:center;">Cargando...</p>';
    try {
        const [resAgents, resStudies] = await Promise.all([
            fetchWithAuth('/api/agents'),
            fetchWithAuth('/api/studies/active')
        ]);
        
        if (!resAgents.ok) { container.innerHTML = '<p>Error cargando encuestadores.</p>'; return; }
        
        const agents = await resAgents.json();
        const studiesData = resStudies.ok ? await resStudies.json() : { active_studies: [] };
        const activeStudies = studiesData.active_studies || [];
        
        if (agents.length === 0) {
            container.innerHTML = '<p style="text-align:center;">No hay usuarios en la base de datos.</p>';
            return;
        }
        
        let html = '<table style="width:100%; border-collapse:collapse; text-align:left;">';
        html += '<tr style="border-bottom:2px solid var(--border-color);"><th>Teléfono</th><th>Nombre / Rol</th><th>Estudios Permitidos</th><th style="text-align:center;">Activo</th></tr>';
        
        agents.forEach(a => {
            const isChecked = a.is_active ? 'checked' : '';
            const assignedArray = a.assigned_studies ? a.assigned_studies.split(',').map(s => s.trim().toLowerCase()) : [];
            
            let checkboxesHtml = '<div style="max-height:80px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:4px; padding:4px; font-size:0.8rem; background:#f8fafc; margin-bottom:4px;">';
            if (activeStudies.length === 0) {
                checkboxesHtml += '<div style="color:#94a3b8; font-style:italic;">No hay estudios activos</div>';
            } else {
                activeStudies.forEach(study => {
                    const checked = assignedArray.includes(study.toLowerCase()) ? 'checked' : '';
                    checkboxesHtml += `<label style="display:block; cursor:pointer; margin-bottom:2px;"><input type="checkbox" class="study-cb-${a.phone_number}" value="${study}" ${checked}> ${study}</label>`;
                });
            }
            checkboxesHtml += '</div>';

            html += `
                <tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:10px 0; font-weight:bold;">${a.phone_number}</td>
                    <td style="padding:10px 0; color:var(--text-main); font-weight:600;">${a.full_name ? a.full_name : a.username} <br><small style="color:var(--text-muted); font-weight:normal;">Usr: ${a.username} (${a.role})</small></td>
                    <td style="padding:10px 0; max-width:200px;">
                        ${checkboxesHtml}
                        <button onclick="saveAgentStudiesCB('${a.phone_number}')" style="padding:4px 8px; font-size:0.75rem; border-radius:4px; background:var(--primary-color); color:white; border:none; cursor:pointer; width:100%; margin-top:2px;">Guardar Estudios</button>
                    </td>
                    <td style="padding:10px 0; text-align:center;">
                        <label style="cursor:pointer;">
                            <input type="checkbox" onchange="toggleAgentStatus('${a.phone_number}', this.checked)" ${isChecked} style="transform: scale(1.5);">
                        </label>
                    </td>
                </tr>
            `;
        });
        html += '</table>';
        container.innerHTML = html;
        
    } catch (e) {
        console.error(e);
        container.innerHTML = '<p>Error de conexión.</p>';
    }
}

async function toggleAgentStatus(phone, isActive) {
    try {
        const res = await fetchWithAuth('/api/agents/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phone, is_active: isActive })
        });
        if (!res.ok) alert("Debes ser Superuser para cambiar accesos.");
    } catch (e) {
        console.error(e);
        alert("Error cambiando el acceso del encuestador.");
    }
}

async function saveAgentStudiesCB(phone) {
    const checkboxes = document.querySelectorAll('.study-cb-' + phone + ':checked');
    const selected = Array.from(checkboxes).map(cb => cb.value).join(',');
    
    try {
        const res = await fetchWithAuth('/api/agents/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phone, assigned_studies: selected })
        });
        if (res.ok) {
            alert('Estudios guardados correctamente.');
        } else {
            const errData = await res.json().catch(() => ({}));
            alert(errData.detail || 'Error al asignar estudios.');
        }
    } catch (e) {
        console.error(e);
        alert('Error de conexión.');
    }
}

// ============================================================
// TDC MODULE - Funciones para estudios de tipo TDC
// ============================================================

function openTdcModal() {
    document.getElementById('tdcModal').style.display = 'flex';
    document.getElementById('tdcStudyCode').value = '';
    document.getElementById('tdcFile').value = '';
}

function closeTdcModal() {
    document.getElementById('tdcModal').style.display = 'none';
}

async function uploadTdc() {
    const studyCode = document.getElementById('tdcStudyCode').value.trim();
    const fileInput = document.getElementById('tdcFile');
    const btn = document.getElementById('btnUploadTdc');
    if (!studyCode) { alert('Ingresa el ID del estudio'); return; }
    if (fileInput.files.length === 0) { alert('Selecciona un archivo Excel'); return; }
    const formData = new FormData();
    formData.append('study_code', studyCode);
    formData.append('file', fileInput.files[0]);
    btn.disabled = true;
    btn.innerText = '⏳ Cargando...';
    try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/quotas/tdc-upload', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        const data = await res.json();
        if (res.ok) { alert(data.msg); closeTdcModal(); loadQuotas(); }
        else { alert(data.detail || 'Error al cargar'); }
    } catch (e) { console.error(e); alert('Error de conexión'); }
    finally { btn.disabled = false; btn.innerText = 'Cargar y Crear'; }
}

// ============================================================
// EXACTA MODULE
// ============================================================

let exactaEPoints = ["Afluencia", "En el barrio", "En frente de edificio"];
let exactaColDims = [
    { id: 'nse', label: 'NSE', values: ["Estrato 2", "Estrato 3", "Estrato 4"], enabled: true },
    { id: 'genero', label: 'G\u00e9nero', values: ["Hombre", "Mujer"], enabled: false },
    { id: 'edad', label: 'Edad', values: ["18-36", "37-40"], enabled: false }
];
let exactaDeletedCols = new Set();

function getExactaCols() {
    const active = exactaColDims.filter(d => d.enabled);
    if (active.length === 0) return [];
    const combos = cartesian(...active.map(d => d.values));
    return combos.map(combo => ({
        label: combo.join(" \u00b7 "),
        parts: combo
    }));
}

function openExactaModal() {
    document.getElementById('exactaModal').style.display = 'flex';
    document.getElementById('exactaStudyCode').value = '';
    document.getElementById('exactaErrorMsg').style.display = 'none';
    exactaEPoints = ["Afluencia", "En el barrio", "En frente de edificio"];
    exactaColDims = [
        { id: 'nse', label: 'NSE', values: ["Estrato 2", "Estrato 3", "Estrato 4"], enabled: true },
        { id: 'genero', label: 'G\u00e9nero', values: ["Hombre", "Mujer"], enabled: false },
        { id: 'edad', label: 'Edad', values: ["18-36", "37-40"], enabled: false }
    ];
    exactaDeletedCols.clear();
    document.getElementById('chkExactaGenero').checked = false;
    document.getElementById('chkExactaEdad').checked = false;
    renderExacta();
}

function closeExactaModal() {
    document.getElementById('exactaModal').style.display = 'none';
}

function toggleExactaDim(dimId, enabled) {
    const d = exactaColDims.find(x => x.id === dimId);
    if (d) { d.enabled = enabled; exactaDeletedCols.clear(); renderExacta(); }
}

function renderExacta() {
    renderExactaDimEditor();
    renderExactaGrid();
}

function renderExactaDimEditor() {
    const c = document.getElementById('exactaDimEditor');
    if (!c) return;
    let h = '';
    exactaColDims.forEach((dim, di) => {
        if (!dim.enabled) return;
        h += '<div style="margin-bottom:6px;padding:6px 10px;background:#fff;border-radius:8px;border:1px solid var(--border-color);display:flex;align-items:center;gap:6px;flex-wrap:wrap;">';
        h += '<span style="font-weight:700;font-size:0.8rem;color:var(--text-muted);white-space:nowrap;">' + dim.label + ':</span>';
        h += '<div style="display:flex;flex-wrap:wrap;gap:4px;flex:1;">';
        dim.values.forEach((val, vi) => {
            h += '<span style="display:inline-flex;align-items:center;gap:2px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:1px 4px;">';
            h += '<input type="text" value="' + val.replace(/"/g, '&quot;') + '" data-di="' + di + '" data-vi="' + vi + '" class="exa-dim-inp" style="width:auto;max-width:100px;border:none;background:transparent;font-weight:600;font-size:0.8rem;padding:2px 4px;">';
            h += '<span onclick="exaRemoveVal(' + di + ',' + vi + ')" style="cursor:pointer;color:#ef4444;font-size:1rem;font-weight:bold;line-height:1;">&times;</span>';
            h += '</span>';
        });
        h += '</div></div>';
    });
    c.innerHTML = h;
    c.querySelectorAll('.exa-dim-inp').forEach(inp => {
        inp.addEventListener('change', function () {
            const di = parseInt(this.dataset.di, 10), vi = parseInt(this.dataset.vi, 10), v = this.value.trim();
            if (!v) { this.value = exactaColDims[di].values[vi]; return; }
            exactaColDims[di].values[vi] = v; exactaDeletedCols.clear(); renderExacta();
        });
    });
}

function exaRemoveVal(di, vi) {
    if (!confirm("Eliminar?")) return;
    exactaColDims[di].values.splice(vi, 1);
    if (exactaColDims[di].values.length === 0) exactaColDims[di].values.push("Nuevo");
    exactaDeletedCols.clear(); renderExacta();
}

function renderExactaGrid() {
    const container = document.getElementById('exactaTableContainer');
    if (!container) return;
    const active = exactaColDims.filter(d => d.enabled);
    if (exactaEPoints.length === 0 || active.length === 0) {
        container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:1rem;">Agrega filas y columnas.</p>'; return;
    }
    const colDim = active[0];
    const cols = colDim.values.filter(v => !exactaDeletedCols.has(v));
    if (cols.length === 0) {
        container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:1rem;">Columnas ocultas.</p>'; return;
    }
    const innerDims = active.slice(1);
    let innerCombos = [[]];
    innerDims.forEach(d => { innerCombos = innerCombos.flatMap(c => d.values.map(v => [...c, v])); });
    const innerLabels = innerCombos.length === 1 && innerCombos[0].length === 0 ? [] : innerCombos.map(combo => combo.join(" \u00b7 "));

    let h = '<div class="htable-container exacta-grid" style="border-width:2px;border-color:#f59e0b;"><div class="htable-root-groups"><div class="htable-group"><div class="htable-cols-container">';
    h += '<div class="htable-cols-row header-row">';
    h += '<div style="min-width:150px;font-weight:800;">Punto</div>';
    cols.forEach(col => {
        h += '<div style="white-space:nowrap;text-align:center;font-weight:700;">' + col + ' <span onclick="exaHideCol(this)" data-col="' + encodeURIComponent(col) + '" style="cursor:pointer;color:#ef4444;font-weight:bold;">&times;</span></div>';
    });
    h += '</div>';
    exactaEPoints.forEach((row, ri) => {
        h += '<div class="htable-cols-row body-row">';
        h += '<div style="font-weight:700;text-align:center;display:flex;align-items:center;justify-content:center;gap:4px;">';
        h += '<input type="text" class="exa-row-inp" value="' + row.replace(/"/g, '&quot;') + '" data-ri="' + ri + '" style="width:100%;border:none;background:transparent;font-weight:700;text-align:center;font-family:inherit;font-size:0.9rem;">';
        h += '<span onclick="exaRemoveRow(' + ri + ')" style="cursor:pointer;color:#ef4444;font-size:1.2rem;font-weight:bold;">&times;</span></div>';
        cols.forEach(col => {
            h += '<div class="exa-cell-wrap">';
            if (innerLabels.length === 0) {
                h += '<input type="number" class="htable-input exa-cell" data-ri="' + ri + '" data-col="' + encodeURIComponent(col) + '" min="0" placeholder="0">';
            } else {
                innerLabels.forEach(il => {
                    const fullLabel = col + " \u00b7 " + il;
                    h += '<div class="exa-inner-row">';
                    h += '<span class="exa-inner-label">' + il + '</span>';
                    h += '<input type="number" class="htable-input exa-cell exa-inner-val" data-ri="' + ri + '" data-col="' + encodeURIComponent(fullLabel) + '" min="0" placeholder="0">';
                    h += '</div>';
                });
            }
            h += '</div>';
        });
        h += '</div>';
    });
    h += '</div></div></div></div>';
    container.innerHTML = h;
    container.querySelectorAll('.exa-row-inp').forEach(inp => {
        inp.addEventListener('change', function () {
            const ri = parseInt(this.dataset.ri, 10);
            if (this.value.trim() === '') this.value = exactaEPoints[ri];
            else exactaEPoints[ri] = this.value.trim();
        });
    });
}

function exaHideCol(el) {
    const col = decodeURIComponent(el.dataset.col);
    if (confirm("Ocultar columna \"" + col + "\"?")) { exactaDeletedCols.add(col); renderExacta(); }
}

function exaRemoveRow(ri) {
    if (!confirm("Eliminar \"" + exactaEPoints[ri] + "\"?")) return;
    exactaEPoints.splice(ri, 1); renderExacta();
}

function addExactaRow() {
    exactaEPoints.push("Nuevo punto"); renderExacta();
    const inps = document.querySelectorAll('.exa-row-inp');
    if (inps.length > 0) inps[inps.length - 1].focus();
}

function addExactaNse() {
    const d = exactaColDims.find(x => x.id === 'nse');
    if (d) { d.values.push("Nuevo"); exactaDeletedCols.clear(); renderExacta(); }
}

function addExactaValor(dimId) {
    const d = exactaColDims.find(x => x.id === dimId);
    if (d) { d.values.push(dimId === 'genero' ? "Otro" : "Nuevo rango"); exactaDeletedCols.clear(); renderExacta(); }
}

async function saveExactaQuotas() {
    const sc = document.getElementById('exactaStudyCode').value.trim();
    const err = document.getElementById('exactaErrorMsg');
    if (!sc) { err.innerText = "Ingresa el ID del estudio"; err.style.display = 'block'; return; }
    const rows = [];
    document.querySelectorAll('.exa-row-inp').forEach(inp => { const v = inp.value.trim(); if (v) rows.push(v); });
    if (rows.length === 0) { err.innerText = "Debes tener al menos un punto"; err.style.display = 'block'; return; }
    const payload = []; let hasVals = false;
    document.querySelectorAll('.exa-cell').forEach(inp => {
        const ri = parseInt(inp.dataset.ri, 10), cl = decodeURIComponent(inp.dataset.col);
        const row = rows[ri], v = parseInt(inp.value, 10);
        if (!row || !cl || isNaN(v) || v <= 0) return;
        hasVals = true;
        payload.push({ study_code: sc, category: "Exacta", value: row + " | " + cl, target_count: v, point_type: row });
    });
    if (!hasVals) { err.innerText = "Ingresa al menos un valor > 0"; err.style.display = 'block'; return; }
    err.style.display = 'none';
    try {
        const res = await fetchWithAuth('/api/quotas/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (res.ok) { closeExactaModal(); loadQuotas(); }
        else { const d = await res.json().catch(() => ({})); err.innerText = "Error: " + (d.detail || 'Error'); err.style.display = 'block'; }
    } catch (e) { console.error(e); err.innerText = "Error de conexi\u00f3n"; err.style.display = 'block'; }
}

function renderExactaGridHtml(quotas) {
    const rows = new Map();
    const colOrder = [];
    const colSeen = new Set();
    const rowOrder = [];
    const innerOrder = [];
    const innerSeen = new Set();

    quotas.forEach(q => {
        const rowName = q.point_type;
        const colPart = q.value.split(" | ").slice(1).join(" | ");
        const parts = colPart.split(" \u00b7 ");
        const colKey = parts[0];
        const innerKey = parts.slice(1).join(" \u00b7 ");

        if (!rows.has(rowName)) { rows.set(rowName, new Map()); rowOrder.push(rowName); }
        const colMap = rows.get(rowName);
        if (!colMap.has(colKey)) colMap.set(colKey, new Map());
        colMap.get(colKey).set(innerKey, q);

        if (!colSeen.has(colKey)) { colSeen.add(colKey); colOrder.push(colKey); }
        if (innerKey && !innerSeen.has(innerKey)) { innerSeen.add(innerKey); innerOrder.push(innerKey); }
    });

    let html = '<div class="htable-container exacta-grid" style="border-width:2px;border-color:#f59e0b;"><div class="htable-root-groups"><div class="htable-group"><div class="htable-cols-container">';
    html += '<div class="htable-cols-row header-row" style="background:#fef3c7;">';
    html += '<div style="min-width:150px;font-weight:800;">Punto</div>';
    colOrder.forEach(col => { html += '<div style="white-space:nowrap;text-align:center;font-weight:700;">' + col + '</div>'; });
    html += '</div>';

    function cellHtml(q) {
        if (!q) return '<div style="color:#94a3b8;font-style:italic;text-align:center;">\u2014</div>';
        const t = q.target_count, cur = q.current_count;
        const pct = t > 0 ? Math.min(100, Math.round((cur / t) * 100)) : 0;
        let c = '#ef4444';
        if (pct >= 100) c = '#3b82f6';
        else if (pct >= 80) c = '#22c55e';
        else if (pct >= 50) c = '#f59e0b';
        return '<div><div class="val-container exa-inner-number"><div class="val-disp">' + cur + '</div><div class="val-target">/ ' + t + '</div></div><div class="progress-bar-bg exa-inner-progress-bg"><div class="progress-bar-fill exa-progress-fill" style="width:' + pct + '%;background:' + c + ';"></div></div></div>';
    }

    rowOrder.forEach(rowName => {
        const colMap = rows.get(rowName);
        html += '<div class="htable-cols-row body-row">';
        html += '<div style="font-weight:700;text-align:center;">' + rowName + '</div>';
        colOrder.forEach(colKey => {
            const innerMap = colMap.get(colKey) || new Map();
            html += '<div class="exa-cell-wrap">';
            if (innerOrder.length === 0) {
                html += cellHtml(innerMap.get(""));
            } else {
                innerOrder.forEach(ik => {
                    const q = innerMap.get(ik);
                    if (q) {
                        const t = q.target_count, cur = q.current_count;
                        const pct = t > 0 ? Math.min(100, Math.round((cur / t) * 100)) : 0;
                        let c = '#ef4444';
                        if (pct >= 100) c = '#3b82f6';
                        else if (pct >= 80) c = '#22c55e';
                        else if (pct >= 50) c = '#f59e0b';
                        html += '<div class="exa-inner-row"><span class="exa-inner-label">' + ik + '</span><div class="exa-inner-val"><div class="val-container exa-inner-number"><div class="val-disp">' + cur + '</div><div class="val-target">/ ' + t + '</div></div><div class="progress-bar-bg exa-inner-progress-bg"><div class="progress-bar-fill exa-progress-fill" style="width:' + pct + '%;background:' + c + ';"></div></div></div></div>';
                    } else {
                        html += '<div class="exa-inner-row"><span class="exa-inner-label">' + ik + '</span><div style="color:#94a3b8;flex:1;text-align:center;">\u2014</div></div>';
                    }
                });
            }
            html += '</div>';
        });
        html += '</div>';
    });

    html += '</div></div></div></div>';
    return html;
}

function renderTdcGridHtml(quotas) {
    const sorted = [...quotas].sort((a, b) => (a.store_id || 0) - (b.store_id || 0));
    const COLS = 5;
    let html = '<div style="display:grid; grid-template-columns:repeat(5,1fr); gap:10px; padding:12px;">';
    sorted.forEach(q => {
        const done = q.current_count >= q.target_count;
        const color = done ? '#10b981' : '#3b82f6';
        const bg = done ? '#d1fae5' : '#eff6ff';
        const storeName = (q.value || '').split(' - ').pop();
        const shortName = storeName.length > 20 ? storeName.substring(0, 18) + '..' : storeName;
        html += `
            <div style="background:${bg}; border:2px solid ${color}; border-radius:10px; padding:10px; text-align:center;">
                <div style="font-size:0.7rem; color:#64748b; text-transform:uppercase; margin-bottom:2px;">${q.category}</div>
                <div style="font-size:1.8rem; font-weight:900; color:#0f172a; line-height:1;">${q.store_id || '?'}</div>
                <div style="font-size:0.72rem; color:#334155; margin:4px 0;">${shortName}</div>
                <div style="font-size:0.8rem; font-weight:700; color:${color};">${q.current_count} / ${q.target_count}</div>
            </div>`;
    });
    html += '</div>';
    return html;
}
