import { useTranslation } from "../lib/locale";
import { useEffect, useState } from 'react';
import { ApiError, signIn } from '../lib/api';
import '../login.css';

export interface LoginScreenProps {
  onLoginSuccess: (email: string) => void;
}

interface DemoAccount {
  role: string;
  name: string;
  email: string;
}

const DEMO_PRESETS: DemoAccount[] = [
  { role: 'Manager', name: 'Priya Menon', email: 'priya.menon@resolva.corp' },
  { role: 'Compliance', name: 'Suresh Kumar', email: 'compliance@resolva.corp' },
  { role: 'Payroll Admin', name: 'Anita Roy', email: 'payroll.admin@resolva.corp' },
];

const REMEMBERED_EMAIL_KEY = 'resolva_remembered_email';

export function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const { tr } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [showForgotNotice, setShowForgotNotice] = useState(false);
  const [signingIn, setSigningIn] = useState(false);

  // Initialize remembered email from localStorage
  useEffect(() => {
    try {
      const savedEmail = localStorage.getItem(REMEMBERED_EMAIL_KEY);
      if (savedEmail) {
        setEmail(savedEmail);
        setRememberMe(true);
      }
    } catch {
      // LocalStorage access might be restricted in some sandboxed environments
    }
  }, []);

  const validate = (): boolean => {
    let isValid = true;
    setEmailError(null);
    setPasswordError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setEmailError('Email address is required.');
      isValid = false;
    } else {
      // Standard email regex format validation
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(trimmedEmail)) {
        setEmailError('Please enter a valid email address (e.g., priya.menon@resolva.corp).');
        isValid = false;
      }
    }

    if (!password.trim()) {
      setPasswordError('The manager access token is required.');
      isValid = false;
    }

    return isValid;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) {
      return;
    }

    const trimmedEmail = email.trim();
    // The token is the identity. The server decides whether it is valid and which employees
    // it may see; nothing here grants access on its own.
    setSigningIn(true);
    try {
      await signIn(password);
    } catch (error) {
      setPasswordError(
        error instanceof ApiError ? error.detail : 'Could not reach the backend. Start it and try again.'
      );
      setSigningIn(false);
      return;
    }
    setSigningIn(false);

    // Security requirement: Remember Me stores ONLY email, NEVER password
    try {
      if (rememberMe) {
        localStorage.setItem(REMEMBERED_EMAIL_KEY, trimmedEmail);
      } else {
        localStorage.removeItem(REMEMBERED_EMAIL_KEY);
      }
    } catch {
      // Storage failure resilience
    }

    onLoginSuccess(trimmedEmail);
  };

  const handleSelectPreset = (preset: DemoAccount) => {
    setEmail(preset.email);
    setEmailError(null);
    setPasswordError(null);
    setShowForgotNotice(false);
  };

  return (
    <div className="login-page">
      <div className="login-container">
        <div className="login-card">
          <header className="login-header">
            <div>
              <span className="login-demo-pill">{tr("Demo Access Only")}</span>
            </div>
            <h1 className="login-brand-title">
              Resolva <span>{tr("Enterprise")}</span>
            </h1>
            <p className="login-subtitle">{tr("Attendance Exception Detection & AI-Assisted Resolution")}</p>
          </header>

          <div className="login-body">
            <div className="login-banner login-banner-info" role="note">
              <strong>{tr("Demo environment:")}</strong>{" " + tr("Access is a bearer token issued by the server, which also decides which employees you can see. Paste the manager token the seed script wrote to backend/local/manager-token.json.")}</div>

            {showForgotNotice && (
              <div className="login-banner login-banner-alert" role="status">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                  <div>
                    <strong>{tr("Demo Mode Notice:")}</strong>{" " + tr("There is no password recovery. Access is a bearer token the server issued; run the seed script to provision one. The name beside it is only a label shown in this interface.")}</div>
                  <button
                    type="button"
                    className="login-dismiss-btn"
                    onClick={() => setShowForgotNotice(false)}
                    aria-label={tr("Dismiss notice")}
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}

            <form className="login-form" onSubmit={handleSubmit} noValidate>
              <div className="login-form-group">
                <label className="login-label" htmlFor="login-email">{tr("Work Email Address")}</label>
                <input
                  id="login-email"
                  type="email"
                  className={`login-input ${emailError ? 'has-error' : ''}`}
                  placeholder="name@company.corp"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailError) setEmailError(null);
                  }}
                  autoComplete="email"
                  aria-invalid={!!emailError}
                  aria-describedby={emailError ? 'email-error' : undefined}
                />
                {emailError && (
                  <div id="email-error" className="login-error-text" role="alert">
                    {tr(emailError)}
                  </div>
                )}
              </div>

              <div className="login-form-group">
                <label className="login-label" htmlFor="login-password">{tr("Manager access token")}</label>
                <div className="login-password-wrapper">
                  <input
                    id="login-password"
                    type={showPassword ? 'text' : 'password'}
                    className={`login-input ${passwordError ? 'has-error' : ''}`}
                    placeholder={tr("Paste the manager access token")}
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (passwordError) setPasswordError(null);
                    }}
                    autoComplete="off"
                    aria-invalid={!!passwordError}
                    aria-describedby={passwordError ? 'password-error' : undefined}
                  />
                  <button
                    type="button"
                    className="login-toggle-pw-btn"
                    onClick={() => setShowPassword((prev) => !prev)}
                    aria-label={tr(showPassword ? 'Hide password' : 'Show password')}
                  >
                    {tr(showPassword ? 'Hide' : 'Show')}
                  </button>
                </div>
                {passwordError && (
                  <div id="password-error" className="login-error-text" role="alert">
                    {tr(passwordError)}
                  </div>
                )}
              </div>

              <div className="login-options-row">
                <label className="login-remember-box">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                  />
                  <span>{tr("Remember my email")}</span>
                </label>

                <button
                  type="button"
                  className="login-forgot-link"
                  onClick={() => setShowForgotNotice(true)}
                >{tr("Forgot password?")}</button>
              </div>

              <button type="submit" className="login-submit-btn" disabled={signingIn}>
                {signingIn ? tr("Checking with the server...") : tr("Sign In to Resolva")}
              </button>
            </form>

            <div className="login-presets-section">
              <div className="login-presets-header">
                <span>{tr("Quick Demo Accounts")}</span>
                <span className="mono" style={{ fontSize: '10px' }}>{tr("Click to Autofill")}</span>
              </div>
              <div className="login-presets-list">
                {DEMO_PRESETS.map((preset) => (
                  <button
                    key={preset.email}
                    type="button"
                    className="login-preset-item"
                    onClick={() => handleSelectPreset(preset)}
                  >
                    <div>
                      <span className="login-preset-name">{preset.name}</span>
                      <span className="muted" style={{ marginLeft: 6 }}>({preset.email})</span>
                    </div>
                    <span className="login-preset-role">{tr(preset.role)}</span>
                  </button>
                ))}
              </div>
            </div>

            <p className="login-disclaimer">{tr("This is a prototype demonstration environment for team evaluation. No production identity provider (SSO / SAML / OAuth) is connected.")}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
