import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/ui.css";
import App from "./App.tsx";
import { AmountVisibilityProvider } from "./context/AmountVisibilityContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AmountVisibilityProvider>
        <App />
      </AmountVisibilityProvider>
    </BrowserRouter>
  </StrictMode>
);
