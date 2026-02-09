# 🎯 PORTAL MANAGEMENT - Vollständige Implementierung

## ÜBERSICHT

Portal Management mit:
- ✅ Portal-Liste speichern (localStorage)
- ✅ Drag & Drop (Sortable.js)
- ✅ Add/Edit/Delete Portale
- ✅ Kategorien
- ✅ Drag to Scanner

---

## SCHRITT 1: Sortable.js einbinden

**In `templates/base.html` (oder in scanner.html direkt)**:

```html
<!-- Vor </body> -->
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js"></script>
```

---

## SCHRITT 2: Portal Management Tab hinzufügen

**In `templates/scanner.html` - Nach dem "Found MACs" Tab**:

```html
<li class="nav-item" role="presentation">
    <button class="nav-link" id="portals-tab" data-bs-toggle="tab" data-bs-target="#portals-panel" type="button" role="tab">
        <i class="ti ti-server me-1"></i>Portal Management
    </button>
</li>
```

**Tab Content hinzufügen**:

```html
<!-- PORTAL MANAGEMENT TAB -->
<div class="tab-pane fade" id="portals-panel" role="tabpanel">
    
    <div class="card mb-3">
        <div class="card-header">
            <h3 class="card-title">Saved Portals</h3>
            <div class="card-actions">
                <button class="btn btn-primary btn-sm" onclick="addPortalDialog()">
                    <i class="ti ti-plus me-1"></i>Add Portal
                </button>
            </div>
        </div>
        <div class="card-body">
            <div class="alert alert-info mb-3">
                <strong>💡 Tip:</strong> Drag portals to reorder. Drag a portal to the "Portal URL" field in the Scan tab to use it.
            </div>
            
            <!-- Portal List -->
            <div id="portalList" class="list-group">
                <!-- Portals werden hier dynamisch eingefügt -->
            </div>
            
            <div id="emptyPortalList" class="text-center text-muted py-4" style="display: none;">
                <i class="ti ti-server" style="font-size: 3rem; opacity: 0.3;"></i>
                <p class="mt-2">No saved portals yet</p>
                <button class="btn btn-primary" onclick="addPortalDialog()">
                    <i class="ti ti-plus me-1"></i>Add Your First Portal
                </button>
            </div>
        </div>
    </div>
    
    <!-- Categories -->
    <div class="card">
        <div class="card-header">
            <h3 class="card-title">Categories</h3>
        </div>
        <div class="card-body">
            <div class="row g-2">
                <div class="col-auto">
                    <span class="badge bg-primary">All (0)</span>
                </div>
                <div class="col-auto">
                    <span class="badge bg-success">Active (0)</span>
                </div>
                <div class="col-auto">
                    <span class="badge bg-warning">Testing (0)</span>
                </div>
                <div class="col-auto">
                    <span class="badge bg-info">Favorites (0)</span>
                </div>
            </div>
        </div>
    </div>
    
</div>
<!-- END PORTAL MANAGEMENT TAB -->
```

---

## SCHRITT 3: JavaScript für Portal Management

**Am Ende von `<script>` in scanner.html**:

```javascript
// ============== PORTAL MANAGEMENT ==============

// Portal Storage
const PORTALS_STORAGE_KEY = 'scanner_saved_portals';

// Load portals from localStorage
function loadPortals() {
    const stored = localStorage.getItem(PORTALS_STORAGE_KEY);
    return stored ? JSON.parse(stored) : [];
}

// Save portals to localStorage
function savePortals(portals) {
    localStorage.setItem(PORTALS_STORAGE_KEY, JSON.stringify(portals));
}

// Render portal list
function renderPortalList() {
    const portals = loadPortals();
    const listEl = document.getElementById('portalList');
    const emptyEl = document.getElementById('emptyPortalList');
    
    if (portals.length === 0) {
        listEl.style.display = 'none';
        emptyEl.style.display = 'block';
        return;
    }
    
    listEl.style.display = 'block';
    emptyEl.style.display = 'none';
    
    listEl.innerHTML = portals.map((portal, index) => `
        <div class="list-group-item portal-item" data-index="${index}" draggable="true">
            <div class="row align-items-center">
                <div class="col-auto">
                    <i class="ti ti-grip-vertical text-muted" style="cursor: move;"></i>
                </div>
                <div class="col">
                    <div class="d-flex align-items-center">
                        <div class="flex-fill">
                            <div class="fw-bold">${portal.name || 'Unnamed Portal'}</div>
                            <div class="text-muted small">${portal.url}</div>
                            ${portal.category ? `<span class="badge bg-${getCategoryColor(portal.category)} mt-1">${portal.category}</span>` : ''}
                        </div>
                    </div>
                </div>
                <div class="col-auto">
                    <button class="btn btn-sm btn-ghost-primary" onclick="usePortal(${index})" title="Use in Scanner">
                        <i class="ti ti-arrow-right"></i>
                    </button>
                    <button class="btn btn-sm btn-ghost-secondary" onclick="editPortal(${index})" title="Edit">
                        <i class="ti ti-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-ghost-danger" onclick="deletePortal(${index})" title="Delete">
                        <i class="ti ti-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
    
    // Initialize Sortable
    initSortable();
}

// Initialize Sortable.js
function initSortable() {
    const listEl = document.getElementById('portalList');
    if (!listEl || listEl.children.length === 0) return;
    
    new Sortable(listEl, {
        animation: 150,
        handle: '.ti-grip-vertical',
        onEnd: function(evt) {
            // Reorder portals
            const portals = loadPortals();
            const item = portals.splice(evt.oldIndex, 1)[0];
            portals.splice(evt.newIndex, 0, item);
            savePortals(portals);
        }
    });
}

// Get category color
function getCategoryColor(category) {
    const colors = {
        'Active': 'success',
        'Testing': 'warning',
        'Favorites': 'info',
        'Inactive': 'secondary'
    };
    return colors[category] || 'primary';
}

// Add portal dialog
function addPortalDialog() {
    const name = prompt('Portal Name:');
    if (!name) return;
    
    const url = prompt('Portal URL:');
    if (!url) return;
    
    const category = prompt('Category (optional):\nActive, Testing, Favorites, or leave empty');
    
    const portal = {
        id: Date.now(),
        name: name,
        url: url,
        category: category || null,
        created: new Date().toISOString()
    };
    
    const portals = loadPortals();
    portals.push(portal);
    savePortals(portals);
    renderPortalList();
    
    showAlert('success', `Portal "${name}" added successfully!`);
}

// Edit portal
function editPortal(index) {
    const portals = loadPortals();
    const portal = portals[index];
    
    const name = prompt('Portal Name:', portal.name);
    if (name === null) return;
    
    const url = prompt('Portal URL:', portal.url);
    if (url === null) return;
    
    const category = prompt('Category (optional):', portal.category || '');
    
    portal.name = name;
    portal.url = url;
    portal.category = category || null;
    portal.updated = new Date().toISOString();
    
    portals[index] = portal;
    savePortals(portals);
    renderPortalList();
    
    showAlert('success', `Portal "${name}" updated successfully!`);
}

// Delete portal
function deletePortal(index) {
    const portals = loadPortals();
    const portal = portals[index];
    
    if (!confirm(`Delete portal "${portal.name}"?`)) return;
    
    portals.splice(index, 1);
    savePortals(portals);
    renderPortalList();
    
    showAlert('success', `Portal "${portal.name}" deleted successfully!`);
}

// Use portal in scanner
function usePortal(index) {
    const portals = loadPortals();
    const portal = portals[index];
    
    // Switch to Scan tab
    document.getElementById('scan-tab').click();
    
    // Fill portal URL
    document.getElementById('portalUrl').value = portal.url;
    
    showAlert('success', `Portal "${portal.name}" loaded into scanner!`);
}

// Initialize portal list on page load
document.addEventListener('DOMContentLoaded', function() {
    renderPortalList();
});

// Drag portal to scanner (advanced)
document.addEventListener('DOMContentLoaded', function() {
    const portalUrlInput = document.getElementById('portalUrl');
    
    // Make portal URL input a drop zone
    portalUrlInput.addEventListener('dragover', (e) => {
        e.preventDefault();
        portalUrlInput.style.borderColor = '#0054a6';
        portalUrlInput.style.backgroundColor = '#f0f8ff';
    });
    
    portalUrlInput.addEventListener('dragleave', (e) => {
        portalUrlInput.style.borderColor = '';
        portalUrlInput.style.backgroundColor = '';
    });
    
    portalUrlInput.addEventListener('drop', (e) => {
        e.preventDefault();
        portalUrlInput.style.borderColor = '';
        portalUrlInput.style.backgroundColor = '';
        
        const index = e.dataTransfer.getData('portal-index');
        if (index) {
            const portals = loadPortals();
            const portal = portals[parseInt(index)];
            if (portal) {
                portalUrlInput.value = portal.url;
                showAlert('success', `Portal "${portal.name}" dropped!`);
            }
        }
    });
});

// Make portal items draggable to scanner
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('portalList').addEventListener('dragstart', (e) => {
        if (e.target.classList.contains('portal-item')) {
            e.dataTransfer.setData('portal-index', e.target.dataset.index);
        }
    });
});
```

---

## SCHRITT 4: CSS Styling

**In `<style>` oder CSS-Datei**:

```css
.portal-item {
    cursor: move;
    transition: all 0.2s;
}

.portal-item:hover {
    background-color: #f8f9fa;
    transform: translateX(5px);
}

.portal-item.sortable-ghost {
    opacity: 0.4;
    background-color: #e9ecef;
}

.portal-item.sortable-drag {
    opacity: 0.8;
}
```

---

## SCHRITT 5: Gleiche Änderungen in scanner-new.html

Kopiere alle Änderungen auch in `templates/scanner-new.html`:
- Tab hinzufügen
- Tab Content hinzufügen
- JavaScript hinzufügen
- CSS hinzufügen

---

## TESTING

### Test 1: Portal hinzufügen
1. Gehe zu "Portal Management" Tab
2. Klicke "Add Portal"
3. Gebe Name und URL ein
4. **Erwarte**: Portal erscheint in Liste

### Test 2: Portal bearbeiten
1. Klicke Edit-Button bei Portal
2. Ändere Name oder URL
3. **Erwarte**: Änderungen gespeichert

### Test 3: Portal löschen
1. Klicke Delete-Button
2. Bestätige
3. **Erwarte**: Portal entfernt

### Test 4: Portal verwenden
1. Klicke Arrow-Button bei Portal
2. **Erwarte**: Wechsel zu Scan Tab, URL gefüllt

### Test 5: Drag & Drop Reorder
1. Ziehe Portal an andere Position
2. **Erwarte**: Reihenfolge gespeichert

### Test 6: Drag to Scanner
1. Ziehe Portal auf "Portal URL" Feld
2. **Erwarte**: URL gefüllt

---

## FEATURES

✅ Portal-Liste mit localStorage  
✅ Add/Edit/Delete Portale  
✅ Drag & Drop Reorder (Sortable.js)  
✅ Drag to Scanner  
✅ Kategorien  
✅ Use Portal Button  
✅ Persistent über Neustarts  

---

## NÄCHSTE SCHRITTE

Nach Implementierung:
1. Pattern Generator UI
2. Scheduler UI

**Status**: Bereit zur Implementierung
