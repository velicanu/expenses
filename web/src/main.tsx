import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { makeQueryClient } from "./hooks";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={makeQueryClient()}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
