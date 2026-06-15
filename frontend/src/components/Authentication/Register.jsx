import { useState, useEffect } from "react";
import "./auth.css";

import {
  getPreferenceOptions,
  savePreferences,
  getPreferences,
  register,
} from "../../lib/api";

const MODE_LABELS = {
  local: "Local",
  student: "Student",
  tourist: "Tourist",
  nomad: "Digital Nomad",
  business: "Business Visitor",
};

const TIER_LABELS = {
  budget: "Budget-friendly",
  mid: "Mid-range",
  premium: "Premium",
  luxury: "Luxury",
};

const INTEREST_LABELS = {
  live_music: "Live music",
  study_work_cafes: "Study & work cafés",
};

const prettify = (token) =>
  token.charAt(0).toUpperCase() + token.slice(1).replace(/_/g, " ");

const label = (map, token) => map[token] || prettify(token);

function Register({ onClose, onSwitch, onSaved, onRegistered, initialStep = 1, setupOnly = false }) {
  const [step, setStep] = useState(initialStep);

  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    cityMode: "",
    budget: "",
    currency: "",
    language: "",
  });

  const [selectedInterests, setSelectedInterests] = useState([]);
  const [selectedAreas, setSelectedAreas] = useState([]);
  const [selectedStyles, setSelectedStyles] = useState([]);
  const [errors, setErrors] = useState({});
  const [isSaving, setIsSaving] = useState(false);

  const [options, setOptions] = useState({
    modes: [],
    price_tiers: [],
    currencies: [],
    interests: [],
  });

  useEffect(() => {
    getPreferenceOptions()
      .then(setOptions)
      .catch((err) => console.error("Failed to load preference options:", err));

    getPreferences()
      .then((prefs) => {
        setFormData((prev) => ({
          ...prev,
          cityMode: prefs.mode || "",
          budget: prefs.price_tier || "",
          currency: prefs.currency || "",
        }));
        setSelectedInterests(prefs.interests || []);
      })
      .catch(() => {});
  }, []);

  const areas = [
    "Blloku",
    "City Center",
    "Liqeni",
    "Pazari i Ri",
    "Dajti",
    "Komuna e Parisit",
    "Arena",
    "21 Dhjetori",
  ];

  const styles = [
    "Calm & scenic",
    "Social & lively",
    "Food-focused",
    "Culture-focused",
    "Nightlife-focused",
    "Quick & practical",
  ];

  const modalClassName =
    step === 2
      ? "auth-modal auth-register-modal setup-mode"
      : "auth-modal auth-register-modal";

  const handleInputChange = (event) => {
    const { name, value } = event.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));

    setErrors((prev) => ({
      ...prev,
      [name]: "",
    }));
  };

  const toggleSelection = (value, selectedValues, setSelectedValues) => {
    if (selectedValues.includes(value)) {
      setSelectedValues(selectedValues.filter((item) => item !== value));
    } else {
      setSelectedValues([...selectedValues, value]);
    }
  };

  const validateStepOne = () => {
    const newErrors = {};

    if (!formData.firstName.trim()) {
      newErrors.firstName = "First name is required.";
    }

    if (!formData.lastName.trim()) {
      newErrors.lastName = "Last name is required.";
    }

    if (!formData.email.trim()) {
      newErrors.email = "Email is required.";
    } else if (!/^\S+@\S+\.\S+$/.test(formData.email)) {
      newErrors.email = "Enter a valid email address.";
    }

    if (!formData.password.trim()) {
      newErrors.password = "Password is required.";
    } else if (formData.password.length < 8) {
      newErrors.password = "Password must be at least 8 characters.";
    }

    if (!formData.cityMode) {
      newErrors.cityMode = "Choose a city mode.";
    }

    setErrors(newErrors);

    return Object.keys(newErrors).length === 0;
  };

  // Step 1 now creates a REAL backend account (email = username), then
  // advances to preferences. Step 2 persists prefs keyed to the account.
  const handleContinue = async () => {
    if (!validateStepOne()) return;
    setIsSaving(true);
    try {
      await register(
        formData.email.trim(),
        formData.password,
        formData.firstName.trim() || formData.email.trim(),
        formData.language || "en"
      );
      onRegistered?.(formData.firstName.trim() || formData.email.trim());
      setStep(2);
    } catch (err) {
      setErrors((prev) => ({
        ...prev,
        email:
          err.status === 409
            ? "An account with this email already exists."
            : "Couldn't create your account. Please try again.",
      }));
    } finally {
      setIsSaving(false);
    }
  };

  const handleFinishSetup = async () => {
    setIsSaving(true);
    try {
      await savePreferences({
        mode: formData.cityMode || null,
        price_tier: formData.budget || null,
        currency: formData.currency || null,
        interests: selectedInterests,
      });
      onSaved?.();
      onClose();
    } catch (err) {
      console.error("Failed to save preferences:", err);
      setErrors((prev) => ({
        ...prev,
        setup: "Couldn’t save your preferences. Please try again.",
      }));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="auth-overlay">
      <div className={modalClassName}>
        <button type="button" className="auth-close" onClick={onClose}>
          ×
        </button>

        {step === 1 ? (
          <>
            <div className="auth-header">
              <span className="auth-pill">Create account</span>

              <h2>Create your profile.</h2>

              <p>
                Save places, choose your interests, and make TiranaTips feel
                more personal.
              </p>
            </div>

            <form className="auth-form">
              <div className="auth-grid-two">
                <div className="form-group">
                  <label>First name</label>
                  <input
                    type="text"
                    name="firstName"
                    placeholder="Sara"
                    value={formData.firstName}
                    onChange={handleInputChange}
                    className={errors.firstName ? "input-error" : ""}
                  />
                  {errors.firstName && (
                    <small className="form-error">{errors.firstName}</small>
                  )}
                </div>

                <div className="form-group">
                  <label>Last name</label>
                  <input
                    type="text"
                    name="lastName"
                    placeholder="Lozi"
                    value={formData.lastName}
                    onChange={handleInputChange}
                    className={errors.lastName ? "input-error" : ""}
                  />
                  {errors.lastName && (
                    <small className="form-error">{errors.lastName}</small>
                  )}
                </div>
              </div>

              <div className="auth-grid-two">
                <div className="form-group">
                  <label>Email address</label>
                  <input
                    type="email"
                    name="email"
                    placeholder="you@example.com"
                    value={formData.email}
                    onChange={handleInputChange}
                    className={errors.email ? "input-error" : ""}
                  />
                  {errors.email && (
                    <small className="form-error">{errors.email}</small>
                  )}
                </div>

                <div className="form-group">
                  <label>Password</label>
                  <input
                    type="password"
                    name="password"
                    placeholder="Create password"
                    value={formData.password}
                    onChange={handleInputChange}
                    className={errors.password ? "input-error" : ""}
                  />
                  {errors.password && (
                    <small className="form-error">{errors.password}</small>
                  )}
                </div>
              </div>

              <div className="form-group">
                <label>City mode</label>
                <select
                  name="cityMode"
                  value={formData.cityMode}
                  onChange={handleInputChange}
                  className={errors.cityMode ? "input-error" : ""}
                >
                  <option value="" disabled>
                    Choose one
                  </option>
                  {options.modes.map((mode) => (
                    <option key={mode} value={mode}>
                      {label(MODE_LABELS, mode)}
                    </option>
                  ))}
                </select>
                {errors.cityMode && (
                  <small className="form-error">{errors.cityMode}</small>
                )}
              </div>

              <div className="form-group">
                <label>App language</label>
                <select
                  name="language"
                  value={formData.language}
                  onChange={handleInputChange}
                >
                  <option value="" disabled>
                    Choose language
                  </option>
                  <option value="en">English</option>
                  <option value="sq">Shqip</option>
                  <option value="it">Italiano</option>
                  <option value="de">Deutsch</option>
                  <option value="fr">Français</option>
                  <option value="es">Español</option>
                  <option value="tr">Türkçe</option>
                  <option value="el">Ελληνικά</option>
                  <option value="ru">Русский</option>
                  <option value="zh">中文</option>
                  <option value="ar">العربية</option>
                </select>
              </div>

              <button
                type="button"
                className="auth-submit"
                onClick={handleContinue}
                disabled={isSaving}
              >
                {isSaving ? "Creating account..." : "Continue"}
              </button>
            </form>

            <div className="auth-switch">
              <p>
                Already have an account?{" "}
                <button type="button" onClick={onSwitch}>
                  Log in
                </button>
              </p>
            </div>
          </>
        ) : (
          <>
            <div className="auth-header">
              <span className="auth-pill">
                {setupOnly ? "Your preferences" : "Step 2 of 2"}
              </span>

              <h2>Personalize your TiranaTips.</h2>

              <p>
                Choose what you like so your city experience feels more
                relevant.
              </p>
            </div>

            <form className="auth-form">
              <div className="setup-section">
                <label>Interests</label>

                <div className="setup-chip-grid">
                  {options.interests.map((interest) => (
                    <button
                      type="button"
                      key={interest}
                      className={
                        selectedInterests.includes(interest)
                          ? "setup-chip-active"
                          : ""
                      }
                      onClick={() =>
                        toggleSelection(
                          interest,
                          selectedInterests,
                          setSelectedInterests
                        )
                      }
                    >
                      {label(INTEREST_LABELS, interest)}
                    </button>
                  ))}
                </div>
              </div>

              <div className="setup-section">
                <label>Preferred areas</label>

                <div className="setup-chip-grid">
                  {areas.map((area) => (
                    <button
                      type="button"
                      key={area}
                      className={
                        selectedAreas.includes(area) ? "setup-chip-active" : ""
                      }
                      onClick={() =>
                        toggleSelection(area, selectedAreas, setSelectedAreas)
                      }
                    >
                      {area}
                    </button>
                  ))}
                </div>
              </div>

              <div className="setup-section">
                <label>Your city style</label>

                <div className="setup-chip-grid">
                  {styles.map((style) => (
                    <button
                      type="button"
                      key={style}
                      className={
                        selectedStyles.includes(style)
                          ? "setup-chip-active"
                          : ""
                      }
                      onClick={() =>
                        toggleSelection(style, selectedStyles, setSelectedStyles)
                      }
                    >
                      {style}
                    </button>
                  ))}
                </div>
              </div>

              <div className="auth-grid-two">
                <div className="form-group">
                  <label>Budget</label>
                  <select
                    name="budget"
                    value={formData.budget}
                    onChange={handleInputChange}
                  >
                    <option value="" disabled>
                      Choose budget
                    </option>
                    {options.price_tiers.map((tier) => (
                      <option key={tier} value={tier}>
                        {label(TIER_LABELS, tier)}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Currency</label>
                  <select
                    name="currency"
                    value={formData.currency}
                    onChange={handleInputChange}
                  >
                    <option value="" disabled>
                      Choose currency
                    </option>
                    {options.currencies.map((currency) => (
                      <option key={currency} value={currency}>
                        {currency}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {errors.setup && (
                <small className="form-error">{errors.setup}</small>
              )}

              <div className="auth-step-actions">
                <button
                  type="button"
                  className="auth-submit"
                  onClick={handleFinishSetup}
                  disabled={isSaving}
                >
                  {isSaving ? "Saving..." : "Finish setup"}
                </button>
              </div>

              <button type="button" className="skip-setup-btn" onClick={onClose}>
                Skip for now
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

export default Register;