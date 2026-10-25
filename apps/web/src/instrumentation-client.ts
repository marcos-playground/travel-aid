import { trackError } from "./lib/analytics";

// No automatic exception SDK: errors may contain chat text or credentials.
window.addEventListener("error", () => trackError("uncaught_client_error", "browser"));
window.addEventListener("unhandledrejection", () => trackError("unhandled_rejection", "browser"));
