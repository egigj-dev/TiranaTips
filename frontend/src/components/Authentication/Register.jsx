import { useState } from "react";
import "./auth.css";

function Register({ onClose, onSwitch, initialStep = 1, setupOnly = false }) {
  const [step, setStep] = useState(initialStep);

  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    password: "",
    cityMode: "",
    budget: "",
    currency: "",
  });

  const [selectedInterests, setSelectedInterests] = useState([]);
  const [selectedAreas, setSelectedAreas] = useState([]);
  const [selectedStyles, setSelectedStyles] = useState([]);
  const [errors, setErrors] = useState({});

  const interests = [
    "Coffee",
    "Restaurants",
    "Nature",
    "Culture",
    "Events",
    "Nightlife",
    "Shopping",
    "Hidden gems",
    "Museums",
    "Study spots",
    "Work-friendly cafés",
    "Day trips",
  ];

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

  const handleContinue = () => {
    if (validateStepOne()) {
      setStep(2);
    }
  };

  const handleFinishSetup = () => {
    console.log({
      ...formData,
      interests: selectedInterests,
      preferredAreas: selectedAreas,
      cityStyles: selectedStyles,
    });

    onClose();
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
                  <option value="Local">Local</option>
                  <option value="Student">Student</option>
                  <option value="Tourist">Tourist</option>
                  <option value="Digital Nomad">Digital Nomad</option>
                  <option value="Business Visitor">Business Visitor</option>
                </select>
                {errors.cityMode && (
                  <small className="form-error">{errors.cityMode}</small>
                )}
              </div>

              <button
                type="button"
                className="auth-submit"
                onClick={handleContinue}
              >
                Continue
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
              <span className="auth-pill">Step 2 of 2</span>

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
                  {interests.map((interest) => (
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
                      {interest}
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
                    <option value="Budget-friendly">Budget-friendly</option>
                    <option value="Mid-range">Mid-range</option>
                    <option value="Premium">Premium</option>
                    <option value="No preference">No preference</option>
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
                    <option value="ALL">ALL</option>
                    <option value="EUR">EUR</option>
                    <option value="USD">USD</option>
                  </select>
                </div>
              </div>

              <div className="auth-step-actions">
                <button
                  type="button"
                  className="auth-secondary-btn"
                  onClick={() => setStep(1)}
                >
                  Back
                </button>

                <button
                  type="button"
                  className="auth-submit"
                  onClick={handleFinishSetup}
                >
                  Finish setup
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