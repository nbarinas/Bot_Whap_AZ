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
    "NSE": ["MT", "MB", "BA"]
};

const PRIORITY_ORDER = ["Género", "Región", "Edad", "NSE"];
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
                    if (!current['Total']) current['Total'] = { __isLeaf: true, __quotas: [] };
                    current['Total'].__quotas.push(q);
                } else {
                    current.__quotas.push(q);
                }
            });

            const html = renderTreeHtml(root, true);

            const statusBadge = isClosed ? '<span style="background:var(--text-muted); color:white; padding:2px 8px; border-radius:10px; margin-left:10px; font-size:0.8rem;"><i class="fas fa-archive"></i> Cerrado</span>' : '';
            const lockIcon = isClosed ? 'fa-lock-open' : 'fa-lock';
            const lockColor = isClosed ? '#10b981' : '#64748b';
            const lockTitle = isClosed ? 'Reabrir Estudio' : 'Cerrar Estudio (Ocultar del bot)';

            const studyWrapper = document.createElement('div');
            studyWrapper.className = 'htable-container';
            studyWrapper.innerHTML = `
                <div class="study-label" style="${isClosed ? 'background: #94a3b8;' : ''}">
                    <span>ESTUDIO: ${studyCode} ${statusBadge} <span style="font-size:0.8rem; background:rgba(255,255,255,0.2); color:white; padding:2px 8px; border-radius:10px; margin-left:10px;">${quotas.length} ítems</span></span>
                    <div style="display:flex; gap: 8px;">
                        <button onclick="toggleStudyStatus('${studyCode}')" style="background:${lockColor}; color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="${lockTitle}"><i class="fas ${lockIcon}"></i></button>
                        <button onclick="editStudy('${studyCode}')" style="background:var(--warning); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Editar Estudio"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteStudyGlobal('${studyCode}')" style="background:var(--danger); color:white; border:none; padding:4px 10px; border-radius:6px; cursor:pointer;" title="Eliminar Estudio"><i class="fas fa-trash-alt"></i></button>
                    </div>
                </div>
                <div class="htable-root-groups" style="${isClosed ? 'opacity:0.6; pointer-events:none;' : ''}">${html}</div>
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
            headerHtml += `<div>${isProposal ? q.val : q.value}</div>`;
            if (isProposal) {
                bodyHtml += `
                    <div>
                        <input type="number" class="htable-input" value="${q.target}" data-cat="${q.dbCat}" data-val="${q.val}" min="0">
                    </div>
                `;
            } else {
                const percent = q.target_count > 0 ? Math.min(100, Math.round((q.current_count / q.target_count) * 100)) : 0;
                let color = '#ef4444';
                if (percent >= 100) color = '#3b82f6';
                else if (percent >= 80) color = '#22c55e';
                else if (percent >= 50) color = '#f59e0b';

                bodyHtml += `
                    <div>
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

function generateProposals() {
    const total = parseInt(document.getElementById('totalSurveys').value, 10) || 0;
    let checkboxes = Array.from(document.querySelectorAll('.category-toggles input[type="checkbox"]:checked')).map(cb => cb.value);

    checkboxes.sort((a, b) => PRIORITY_ORDER.indexOf(a) - PRIORITY_ORDER.indexOf(b));
    const container = document.getElementById('proposalsContainer');
    container.innerHTML = '';

    if (total <= 0) return;

    if (checkboxes.length === 0) {
        container.innerHTML = `
        <div class="htable-container" style="border-width:1px; margin-bottom:0;">
            <div class="htable-cols-container">
                <div class="htable-cols-row header-row"><div>Total General</div></div>
                <div class="htable-cols-row body-row">
                    <div><input type="number" class="htable-input" value="${total}" data-cat="General" data-val="Total" min="1"></div>
                </div>
            </div>
        </div>`;
        return;
    }

    const minorCat = checkboxes[checkboxes.length - 1];
    const majorCats = checkboxes.slice(0, checkboxes.length - 1);

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
                dbCat: dbCategory
            });
        });
    });

    const html = renderTreeHtml(root, true, 0, true);
    container.innerHTML = `<div class="htable-container" style="border-width:1px; margin-bottom:0;"><div class="htable-root-groups">${html}</div></div>`;
}

function openModal() {
    document.getElementById('quotaModal').style.display = 'flex';
    document.getElementById('studyCode').value = '';
    document.getElementById('totalSurveys').value = '';
    document.getElementById('studyCode').readOnly = false;
    document.querySelectorAll('.category-toggles input[type="checkbox"]').forEach(cb => cb.checked = false);

    const ageContainer = document.getElementById('dynamicAgeContainer');
    if (ageContainer) {
        ageContainer.style.display = 'none';
        document.getElementById('ageInputsList').innerHTML = `
            <input type="text" class="age-input-field" value="18-30" style="width:100px; padding:6px; border:1px solid #ccc; border-radius:5px; text-align:center; font-weight:600;" oninput="generateProposals()">
            <input type="text" class="age-input-field" value="31-45" style="width:100px; padding:6px; border:1px solid #ccc; border-radius:5px; text-align:center; font-weight:600;" oninput="generateProposals()">
        `;
    }

    document.getElementById('proposalsContainer').innerHTML = '';
}

function closeModal() { document.getElementById('quotaModal').style.display = 'none'; }

async function saveBatchQuotas() {
    const studyCode = document.getElementById('studyCode').value.trim();
    if (!studyCode) { alert("Ingresa el ID del estudio"); return; }

    const payload = [];
    document.querySelectorAll('.htable-input').forEach(input => {
        const cat = input.getAttribute('data-cat');
        const val = input.getAttribute('data-val');
        const target = parseInt(input.value, 10);
        if (target > 0) {
            payload.push({ study_code: studyCode, category: cat, value: val, target_count: target });
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
    if (confirm("Si rediseñas las agrupaciones (ej. agregar Género) las cuotas viejas se mantendrán y causarán conflicto. Es recomendable Eliminar el estudio y crearlo desde cero si cambiaste la estructura de árbol. ¿Deseas solo actualizar los objetivos de la estructura actual?")) {
        document.getElementById('quotaModal').style.display = 'flex';
        document.getElementById('studyCode').value = studyCode;
        document.getElementById('studyCode').readOnly = true;
        document.getElementById('totalSurveys').value = '';
        document.getElementById('proposalsContainer').innerHTML = '';
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

        responseBox.innerText = data.reply || "Error sin respuesta.";
        responseBox.style.color = data.reply.includes('❌') ? 'var(--danger)' : '#166534';
        responseBox.style.borderColor = data.reply.includes('❌') ? 'var(--danger)' : '#22c55e';

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
        html += '<tr style="border-bottom:2px solid var(--border-color);"><th>Teléfono</th><th>Usuario / Rol</th><th style="text-align:center;">Acceso al Bot</th></tr>';
        
        agents.forEach(a => {
            const isChecked = a.is_active ? 'checked' : '';
            html += `
                <tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:10px 0; font-weight:bold;">${a.phone_number}</td>
                    <td style="padding:10px 0; color:var(--text-muted);">${a.username} <small>(${a.role})</small></td>
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

