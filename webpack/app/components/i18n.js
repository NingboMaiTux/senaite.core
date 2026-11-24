/* i18n integration. This is forked from jarn.jsi18n
 *
 * This is a singleton.
 * Configuration is done on the body tag data-i18ncatalogurl attribute
 *     <body data-i18ncatalogurl="/plonejsi18n">
 *
 *  Or, it'll default to "/plonejsi18n"
 */

import $ from "jquery";


var I18N = function() {
  var self = this;
  self.baseUrl = $('body').attr('data-i18ncatalogurl');
  self.version = $('body').attr('data-i18n-version');
  self.currentLanguage = $('html').attr('lang') || 'en';

  // Fix for country specific languages
  if (self.currentLanguage.split('-').length > 1) {
    self.currentLanguage = self.currentLanguage.split('-')[0] + '_' + self.currentLanguage.split('-')[1].toUpperCase();
  }

  self.storage = null;
  self.catalogs = {};
  self.ttl = 24 * 3600 * 1000;

  // Internet Explorer 8 does not know Date.now() which is used in e.g. loadCatalog, so we "define" it
  if (!Date.now) {
    Date.now = function() {
      return new Date().valueOf();
    };
  }

  try {
    if ('localStorage' in window && window.localStorage !== null && 'JSON' in window && window.JSON !== null) {
      self.storage = window.localStorage;
    }
  } catch (e) {}

  self.configure = function(config) {
    for (var key in config){
      self[key] = config[key];
    }
  };

  self._setCatalog = function (domain, language, catalog) {
    if (domain in self.catalogs) {
      self.catalogs[domain][language] = catalog;
    } else {
      self.catalogs[domain] = {};
      self.catalogs[domain][language] = catalog;
    }
  };

  self._cacheKey = function (domain, language) {
    return 'i18n:' + self.baseUrl + ':' + domain + ':' + language;
  };

  self._storeCatalog = function (domain, language, catalog) {
    if (!self.storage || !self.version || catalog === null) return;
    try {
      self.storage.setItem(self._cacheKey(domain, language), JSON.stringify({
        version: self.version, updated: Date.now(), catalog: catalog
      }));
    } catch (e) { /* Storage may be full or disabled. */ }
  };

  self.getUrl = function(domain, language) {
    return self.baseUrl + '?domain=' + encodeURIComponent(domain) +
      '&language=' + encodeURIComponent(language) +
      (self.version ? '&v=' + encodeURIComponent(self.version) : '');
  };

  self.loadCatalog = function (domain, language) {
    if (language === undefined) {
      language = self.currentLanguage;
    }
    if (self.storage && self.version) {
      try {
        var cached = JSON.parse(self.storage.getItem(self._cacheKey(domain, language)));
        if (cached && cached.version === self.version && cached.catalog &&
            Date.now() - cached.updated < self.ttl) {
          self._setCatalog(domain, language, cached.catalog);
          return;
        }
      } catch (e) { /* An unreadable entry is replaced after the fetch. */ }
    }
    if (!self.baseUrl) {
      return;
    }
    $.getJSON(self.getUrl(domain, language), function (catalog) {
      if (catalog === null) {
        return;
      }
      self._setCatalog(domain, language, catalog);
      self._storeCatalog(domain, language, catalog);
    });
  };

  self.MessageFactory = function (domain, language) {
    language = language || self.currentLanguage;
    return function translate (msgid, keywords) {
      var msgstr;
      if ((domain in self.catalogs) && (language in self.catalogs[domain]) && (msgid in self.catalogs[domain][language])) {
        msgstr = self.catalogs[domain][language][msgid];
      } else {
        msgstr = msgid;
      }
      if (keywords) {
        var regexp, keyword;
        for (keyword in keywords) {
          if (keywords.hasOwnProperty(keyword)) {
            regexp = new RegExp('\\$\\{' + keyword + '\\}', 'g');
            msgstr = msgstr.replace(regexp, keywords[keyword]);
          }
        }
      }
      return msgstr;
    };
  };
};

export default I18N;
