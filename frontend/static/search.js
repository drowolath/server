// CommonTrace — Client-side search & tag filtering
(function () {
  const input = document.getElementById('search');
  const traceList = document.getElementById('trace-list');
  const resultsCount = document.getElementById('results-count');
  const noResults = document.getElementById('no-results');

  if (!input || !traceList) return;

  const cards = Array.from(traceList.querySelectorAll('.trace-card'));
  const totalCount = cards.length;

  // Tag sidebar filtering
  const tagLinks = document.querySelectorAll('.tag-link[data-tag]');
  let activeTag = null;

  tagLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      e.preventDefault();
      const tag = this.dataset.tag;

      if (activeTag === tag) {
        // Deselect
        activeTag = null;
        this.classList.remove('active');
      } else {
        // Select new tag
        tagLinks.forEach(function (l) { l.classList.remove('active'); });
        activeTag = tag;
        this.classList.add('active');
      }

      applyFilters();
    });
  });

  // Search input filtering
  let debounceTimer;
  input.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilters, 150);
  });

  // Read initial tag from URL hash
  if (window.location.hash) {
    var hashTag = decodeURIComponent(window.location.hash.slice(1));
    tagLinks.forEach(function (link) {
      if (link.dataset.tag === hashTag) {
        activeTag = hashTag;
        link.classList.add('active');
      }
    });
    applyFilters();
  }

  function applyFilters() {
    var query = input.value.trim().toLowerCase();
    var terms = query ? query.split(/\s+/) : [];
    var visibleCount = 0;

    cards.forEach(function (card) {
      var searchText = card.dataset.search || '';
      var cardTags = card.dataset.tags || '';

      // Tag filter
      var tagMatch = !activeTag || cardTags.split(',').indexOf(activeTag) !== -1;

      // Text search
      var textMatch = terms.length === 0 || terms.every(function (term) {
        return searchText.indexOf(term) !== -1;
      });

      if (tagMatch && textMatch) {
        card.style.display = '';
        visibleCount++;
      } else {
        card.style.display = 'none';
      }
    });

    // Update count
    if (resultsCount) {
      if (!query && !activeTag) {
        resultsCount.textContent = 'Showing all ' + totalCount + ' traces';
      } else {
        var label = visibleCount === 1 ? ' trace' : ' traces';
        var parts = [];
        if (query) parts.push('"' + query + '"');
        if (activeTag) parts.push('#' + activeTag);
        resultsCount.textContent = visibleCount + label + ' matching ' + parts.join(' + ');
      }
    }

    // No results message
    if (noResults) {
      noResults.style.display = visibleCount === 0 ? 'block' : 'none';
    }

    // Update URL hash
    if (activeTag) {
      history.replaceState(null, '', '#' + encodeURIComponent(activeTag));
    } else if (!query) {
      history.replaceState(null, '', window.location.pathname);
    }
  }
})();
