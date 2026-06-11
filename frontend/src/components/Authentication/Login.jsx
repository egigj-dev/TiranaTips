import "./auth.css";

function Login({ onClose, onSwitch }) {
  return (
    <div className="auth-overlay">
      <div className="auth-modal auth-login-modal">
        <button type="button" className="auth-close" onClick={onClose}>
          ×
        </button>

        <div className="auth-header">
          <span className="auth-pill">Welcome back</span>

          <h2>Login to your personal space.</h2>

          <p>
            Continue to your saved places, preferences, and TiranaTips profile.
          </p>
        </div>

        <form className="auth-form">
          <div className="form-group">
            <label>Email address</label>
            <input type="email" placeholder="you@example.com" />
          </div>

          <div className="form-group">
            <label>Password</label>
            <input type="password" placeholder="Enter your password" />
          </div>

          <div className="login-options">
            <label>
              <input type="checkbox" />
              <span>Remember me</span>
            </label>

            <button type="button">Forgot password?</button>
          </div>

          <button type="button" className="auth-submit">
            Login
          </button>
        </form>

        <div className="auth-switch">
          <p>
            New to TiranaTips?{" "}
            <button type="button" onClick={onSwitch}>
              Create account
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default Login;