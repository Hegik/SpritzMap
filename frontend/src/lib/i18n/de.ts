const de = {
  // Navigation / Header
  nav: {
    logout: 'Abmelden',
    login: 'Anmelden',
  },

  // Filter Panel
  filter: {
    toggle_aria: 'Filter ein-/ausblenden',
    label: 'Filter',
    drink: 'Spritz',
    price: 'Preis',
  },

  // Auth Modal
  auth: {
    heading_login: 'Einloggen',
    heading_register: 'Registrieren',
    heading_forgot: 'Passwort vergessen',
    label_email: 'E-Mail',
    label_username: 'Nutzername',
    label_password: 'Passwort',
    btn_login: 'Einloggen',
    btn_register: 'Registrieren',
    btn_send_link: 'Link senden',
    btn_loading: 'Lädt…',
    switch_to_register: 'Noch kein Konto? Registrieren',
    switch_to_login: 'Schon ein Konto? Einloggen',
    back_to_login: 'Zurück zum Login',
    forgot_password: 'Passwort vergessen?',
    info_registered: 'Registrierung erfolgreich — Öffne bitte dein E-Mail-Postfach und klicke auf den Bestätigungslink.',
    info_reset_sent: 'E-Mail mit Link zum Zurücksetzen des Passworts wurde gesendet',
    error_generic: 'Fehler',
  },

  // Price Submit Modal
  submit: {
    heading: 'Spritz hinzufügen',
    label_drink: 'Spritz-Sorte',
    label_price: 'Preis (€)',
    label_intensity: 'Mischverhältnis',
    label_note: 'Notiz (optional)',
    placeholder_price: 'z.B. 7,50',
    placeholder_note: 'z.B. nur am Wochenende',
    btn_submit: 'Spritz hinzufügen',
    btn_loading: 'Speichern…',
    btn_unavailable: 'Diesen Spritz gibt es hier nicht',
    btn_no_spritz: 'Hier gibt es generell keinen Spritz',
    success: 'Gespeichert!',
    error_save: 'Fehler beim Speichern',
    error_generic: 'Fehler',
  },

  // Map Popups
  map: {
    locate: 'Mein Standort',
    popup_no_price_for_drink: 'Hier wurde noch kein Spritz erfasst.',
    popup_no_price: 'Noch kein Preis erfasst',
    popup_other_drinks: 'Weitere Sorten',
    btn_add_spritz: 'Spritz hinzufügen',
  },

  // Email Verify Page
  verify: {
    loading: 'Wird überprüft…',
    success_heading: '✓ E-Mail bestätigt',
    success_body: 'Dein Konto ist jetzt aktiv. Bitte logge dich ein.',
    error_heading: 'Ungültiger Link',
    error_body: 'Der Link ist abgelaufen oder wurde bereits verwendet.',
    to_map: 'Zur Karte',
  },

  // Reset Password Page
  reset: {
    error_mismatch: 'Passwörter stimmen nicht überein',
    error_too_short: 'Mindestens 8 Zeichen',
    error_generic: 'Fehler',
    success_heading: 'Passwort geändert',
    success_body: 'Du kannst dich jetzt mit deinem neuen Passwort einloggen.',
    label_new_password: 'Neues Passwort',
    label_repeat: 'Wiederholen',
    btn_submit: 'Passwort ändern',
    btn_loading: 'Wird gespeichert…',
    to_map: 'Zur Karte',
  },
};

export default de;
export type Translations = typeof de;
