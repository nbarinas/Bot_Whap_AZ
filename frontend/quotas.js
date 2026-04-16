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
            const isClosed = quotas.length > 0 && quotas[0].is_closed === 1;
            if (isClosed && !showClosed) continue;
            
            const stdRoot = {};
            const ptRoot = {};

            quotas.forEach(q => {
                if (q.value && q.value.startsWith("Censos")) return;
                
                if (q.category === "Tipo de Punto") {
                    // It's a point type quota
                    if (!ptRoot["Tipo de Punto"]) ptRoot["Tipo de Punto"] = { __isLeaf: true, __quotas: [] };
                    ptRoot["Tipo de Punto"].__quotas.push(q);
                } else {
                    // Normal demographic quota
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
            // We don't necessarily need enrichWithTotals for ptRoot if it's just one flat row, 
            // but let's do it if there's more than one leaf? No, ptRoot is flat.
            
            const stdHtml = renderTreeHtml(stdRoot, true);
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
                    <span>ESTUDIO: ${studyCode} ${statusBadge} <span style="font-size:0.8rem; background:rgba(255,255,255,0.2); color:white; padding:2px 8px; border-radius:10px; margin-left:10px;">${quotas.length} ítems</span></span>
                    <div style="display:flex; gap: 8px;">
                        <button onclick="toggleStudyStatus('${studyCode}')" style="background:${lockColor}; color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="${lockTitle}"><i class="fas ${lockIcon}"></i></button>
                        <button onclick="exportStudyData('${studyCode}')" style="background:#16a34a; color:white; border:none; padding:4px 12px; border-radius:6px; cursor:pointer; font-weight:bold; display:flex; align-items:center; gap:5px;" title="Descargar Reporte Excel">
                           <i class="fas fa-file-excel"></i> <span>Reporte</span>
                        </button>
                        <button onclick="editStudy('${studyCode}')" style="background:var(--warning); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Editar Estudio"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteStudyGlobal('${studyCode}')" style="background:var(--danger); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Eliminar Estudio"><i class="fas fa-trash-alt"></i></button>
                    </div>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 20px; padding: 15px; background: #fff; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; ${isClosed ? 'opacity:0.6; pointer-events:none;' : ''}">
                    ${ptHtml ? `
                    <div style="flex: 1 1 300px; min-width: 300px;">
                        <h4 style="color:var(--primary); margin-bottom:0.8rem; font-size:1rem;"><i class="fas fa-map-marker-alt"></i> Cuota de Tipos de Puntos</h4>
                        <div class="htable-root-groups" style="border:1px solid #e2e8f0; border-radius:8px; overflow:hidden;">${ptHtml}</div>
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
    document.getElementById('pointType').value = 'General';
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

    const payload = [];
    document.querySelectorAll('.htable-input').forEach(input => {
        const cat = input.getAttribute('data-cat');
        const val = input.getAttribute('data-val');
        const rowPoint = input.getAttribute('data-point') || 'General';
        const target = parseInt(input.value, 10);
        if (target >= 0) {
            payload.push({ study_code: studyCode, category: cat, value: val, target_count: target, point_type: rowPoint });
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

async function deleteStudyGlobal(studyCode) {
    if (!confirm(`¿Estás completamente seguro de ELIMINAR todo el estudio ${studyCode}?`)) return;
    try {
        const res = await fetchWithAuth(`/api/quotas/study/${studyCode}`, { method: 'DELETE' });
        if (res.ok) loadQuotas();
        else alert("Error al eliminar el estudio");
    } catch (e) {
        console.error(e);
    }
}

function editStudy(studyCode) {
    if (confirm("¿Quieres editar los objetivos de cuota para el estudio " + studyCode + "?")) {
        // Fetch current quotas for this study to populate the modal
        fetchWithAuth('/api/quotas?study_code=' + studyCode)
            .then(res => res.json())
            .then(data => {
                const quotas = data[studyCode];
                if (!quotas) return;

                openModal();
                document.getElementById('studyCode').value = studyCode;
                document.getElementById('studyCode').readOnly = true;
                // Note: We don't restore checkboxes/categories easily here for now as it's a batch edit
                
                // We show them in a simplified tree in the proposals container
                const root = {};
                quotas.forEach(q => {
                    const parts = q.category === "General" ? [] : q.category.split(" | ");
                    let current = root;
                    parts.forEach((p, idx) => {
                        if (!current[p]) {
                            current[p] = (idx === parts.length - 1) ? { __isLeaf: true, __quotas: [] } : {};
                        }
                        current = current[p];
                    });
                    if (parts.length === 0) {
                        if (!current['General']) current['General'] = { __isLeaf: true, __quotas: [] };
                        current = current['General'];
                    }
                    current.__quotas.push({ val: q.value, target: q.target_count, dbCat: q.category });
                });

                const html = renderTreeHtml(root, true, 0, true);
                document.getElementById('proposalsContainer').innerHTML = `<div class="htable-container" style="border-width:1px; margin-bottom:0;"><div class="htable-root-groups">${html}</div></div>`;
            });
    }
}

async function exportStudyData(studyCode) {
    try {
        const token = localStorage.getItem('token');
        const response = await fetch(`/api/export-data/${studyCode}`);
        if (!response.ok) throw new Error("Error al descargar");
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `data_${studyCode}.csv`;
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

async function toggleStudyStatus(studyCode) {
    if (!confirm(`¿Deseas cambiar el estado (Abrir/Cerrar) del estudio ${studyCode}?`)) return;
    try {
        const res = await fetchWithAuth(`/api/quotas/study/${studyCode}/toggle-status`, { method: 'PUT' });
        if (res.ok) loadQuotas();
    } catch (e) { console.error(e); }
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
        const res = await fetchWithAuth('/api/agents');
        if (!res.ok) { container.innerHTML = '<p>Error cargando encuestadores.</p>'; return; }
        const agents = await res.json();
        
        if (agents.length === 0) {
            container.innerHTML = '<p style="text-align:center;">No hay usuarios en la base de datos.</p>';
            return;
        }
        
        let html = '<table style="width:100%; border-collapse:collapse; text-align:left;">';
        html += '<tr style="border-bottom:2px solid var(--border-color);"><th>Teléfono</th><th>Nombre / Rol</th><th style="text-align:center;">Acceso al Bot</th></tr>';
        
        agents.forEach(a => {
            const isChecked = a.is_active ? 'checked' : '';
            html += `
                <tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:10px 0; font-weight:bold;">${a.phone_number}</td>
                    <td style="padding:10px 0; color:var(--text-main); font-weight:600;">${a.full_name ? a.full_name : a.username} <br><small style="color:var(--text-muted); font-weight:normal;">Usr: ${a.username} (${a.role})</small></td>
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
