import React from "react";
import ReactDOM from "react-dom/client";
import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-quartz.css";
import "./index.css";
import App from "./App";
import PortalPage from "./pages/portal/PortalPage";

// Clients open /portal/<their private link>; everyone else gets the freelancer app.
const portalToken = window.location.pathname.match(/^\/portal\/([^/]+)/)?.[1];

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {portalToken ? <PortalPage token={decodeURIComponent(portalToken)} /> : <App />}
  </React.StrictMode>,
);
