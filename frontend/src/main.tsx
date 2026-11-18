import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import { AuthenticatedApp } from "@/components/authenticated-app"
import { ThemeProvider } from "@/components/theme-provider.tsx"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <AuthenticatedApp />
    </ThemeProvider>
  </StrictMode>
)
