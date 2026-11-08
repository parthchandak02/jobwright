// Minimal stand-in for the react-select / Ashby comboboxes: an input with
// role=combobox whose listbox (aria-controls) shows role=option rows from
// data-options ("a|b|c"), filtered by the typed text; clicking a row sets the value.
document.addEventListener('DOMContentLoaded', () => {
  for (const input of document.querySelectorAll('input[role=combobox]')) {
    const list = document.getElementById(input.getAttribute('aria-controls'));
    const all = (list.dataset.options || '').split('|').filter(Boolean);
    const render = () => {
      const q = input.value.toLowerCase();
      list.innerHTML = '';
      for (const opt of all.filter(o => !q || o.toLowerCase().includes(q) || input.dataset.chosen)) {
        const row = document.createElement('div');
        row.setAttribute('role', 'option');
        row.textContent = opt;
        row.addEventListener('click', () => {
          input.value = opt;
          input.dataset.chosen = opt;
          list.style.display = 'none';
        });
        list.appendChild(row);
      }
      list.style.display = list.children.length ? 'block' : 'none';
    };
    input.addEventListener('focus', render);
    input.addEventListener('input', () => { delete input.dataset.chosen; render(); });
  }
  for (const form of document.querySelectorAll('form')) {
    form.addEventListener('submit', () => { window.__submitted = (window.__submitted || 0) + 1; });
  }
});
