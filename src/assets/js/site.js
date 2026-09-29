/*
 * ADSS — site.js
 * Small progressive enhancements. No dependencies, no storage, no cookies.
 *   1. Mobile navigation panel (below 1024 px)
 *   2. Contact form: inline validation + fetch() submission to Formspree
 */
(function () {
  'use strict';

  var root = document.documentElement;
  root.classList.add('js');

  /* ------------------------------------------------------------------
   * 1. Mobile navigation
   * ------------------------------------------------------------------ */
  var toggle = document.querySelector('.nav-toggle');
  var panel = document.getElementById('site-menu');
  var desktop = window.matchMedia('(min-width: 1024px)');
  var isOpen = false;

  function outsideRegions() {
    return [document.querySelector('main'), document.querySelector('.site-footer'), document.querySelector('.brand')];
  }

  function setInert(on) {
    outsideRegions().forEach(function (el) {
      if (!el) return;
      if (on) el.setAttribute('inert', '');
      else el.removeAttribute('inert');
    });
  }

  function trapItems() {
    var items = Array.prototype.slice.call(panel.querySelectorAll('a[href], button:not([disabled])'));
    return [toggle].concat(items);
  }

  function openMenu() {
    isOpen = true;
    toggle.setAttribute('aria-expanded', 'true');
    panel.classList.add('is-open');
    root.classList.add('nav-open');
    setInert(true);
    var first = panel.querySelector('a[href]');
    if (first) first.focus();
  }

  function closeMenu(returnFocus) {
    if (!isOpen) return;
    isOpen = false;
    toggle.setAttribute('aria-expanded', 'false');
    panel.classList.remove('is-open');
    root.classList.remove('nav-open');
    setInert(false);
    if (returnFocus) toggle.focus();
  }

  if (toggle && panel) {
    toggle.addEventListener('click', function () {
      if (isOpen) closeMenu(true);
      else openMenu();
    });

    panel.addEventListener('click', function (event) {
      if (isOpen && event.target.closest('a[href]')) closeMenu(false);
    });

    document.addEventListener('keydown', function (event) {
      if (!isOpen) return;
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        closeMenu(true);
        return;
      }
      if (event.key !== 'Tab') return;
      var items = trapItems();
      var first = items[0];
      var last = items[items.length - 1];
      var index = items.indexOf(document.activeElement);
      if (event.shiftKey && (index <= 0)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (index === -1 || index === items.length - 1)) {
        event.preventDefault();
        first.focus();
      }
    });

    var onBreakpoint = function (mq) {
      if (mq.matches) closeMenu(false);
    };
    if (desktop.addEventListener) desktop.addEventListener('change', onBreakpoint);
    else if (desktop.addListener) desktop.addListener(onBreakpoint);
  }

  /* ------------------------------------------------------------------
   * 2. Contact form
   * ------------------------------------------------------------------ */
  var form = document.querySelector('form[data-enhance]');
  if (!form || !window.fetch || !window.FormData) return;

  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  var MESSAGES = {
    name: { required: 'Please enter your name.' },
    company: { required: 'Please enter your company.' },
    email: {
      required: 'Please enter your work email.',
      invalid: 'Please enter a valid email address, for example name@company.com.'
    },
    message: {
      required: 'Please tell us what you would like to test or discuss.',
      short: 'Please write at least 20 characters.'
    }
  };
  var SUCCESS = "Thank you — we'll reply within two business days.";
  var FAILURE = 'Something went wrong. Please email us at ';

  var fields = ['name', 'company', 'email', 'message'].map(function (n) {
    return form.elements[n];
  });
  var status = form.querySelector('.form-status');
  var submit = form.querySelector('button[type="submit"]');
  var submitLabel = submit.textContent;
  var attempted = false;

  form.setAttribute('novalidate', '');

  function errorFor(field) {
    var value = field.value.trim();
    var msg = MESSAGES[field.name];
    if (!value) return msg.required;
    if (field.name === 'email' && !EMAIL_RE.test(value)) return msg.invalid;
    if (field.name === 'message' && value.length < 20) return msg.short;
    return '';
  }

  function showError(field, text) {
    var id = field.id + '-error';
    var node = document.getElementById(id);
    if (text) {
      if (!node) {
        node = document.createElement('p');
        node.className = 'field-error';
        node.id = id;
        field.insertAdjacentElement('afterend', node);
      }
      node.textContent = text;
      field.setAttribute('aria-invalid', 'true');
      field.setAttribute('aria-describedby', id);
    } else {
      if (node) node.remove();
      field.removeAttribute('aria-invalid');
      field.removeAttribute('aria-describedby');
    }
  }

  function validate(field) {
    var text = errorFor(field);
    showError(field, text);
    return !text;
  }

  function setStatus(kind, text, withMail) {
    status.className = 'form-status' + (kind ? ' is-' + kind : '');
    status.textContent = text || '';
    if (withMail) {
      var link = document.createElement('a');
      link.href = 'mailto:info@adss.ai';
      link.textContent = 'info@adss.ai';
      status.appendChild(link);
      status.appendChild(document.createTextNode('.'));
    }
  }

  function setBusy(busy) {
    submit.disabled = busy;
    submit.textContent = busy ? 'Sending…' : submitLabel;
    form.setAttribute('aria-busy', busy ? 'true' : 'false');
  }

  fields.forEach(function (field) {
    field.addEventListener('blur', function () {
      if (attempted || field.value.trim()) validate(field);
    });
    field.addEventListener('input', function () {
      if (field.getAttribute('aria-invalid') === 'true') validate(field);
    });
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    attempted = true;
    var invalid = fields.filter(function (f) { return !validate(f); });
    if (invalid.length) {
      setStatus('', '');
      invalid[0].focus();
      return;
    }

    setBusy(true);
    setStatus('info', 'Sending…');
    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: { Accept: 'application/json' }
    })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        form.reset();
        attempted = false;
        setStatus('success', SUCCESS);
      })
      .catch(function () {
        setStatus('error', FAILURE, true);
      })
      .then(function () {
        setBusy(false);
      });
  });
})();
