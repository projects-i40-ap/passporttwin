import React from "react";
import ReactDOM from "react-dom/client";


function App() {
  return (
    <main
      style={{
        fontFamily: "Arial, sans-serif",
        maxWidth: "900px",
        margin: "0 auto",
        padding: "40px 24px",
      }}
    >
      <h1>PassportTwin</h1>

      <h2>Document Review</h2>

      <p>
        Human-in-the-loop document ingestion and review interface.
      </p>

      <p>
        Frontend React/Vite environment is running.
      </p>
    </main>
  );
}


ReactDOM.createRoot(
  document.getElementById("root")
).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);