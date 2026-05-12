import { Route, Routes } from "react-router-dom";

import { AppShell } from "./components/layout/AppShell";
import { ConversationPage } from "./pages/ConversationPage";
import { HistoryPage } from "./pages/HistoryPage";
import { HomePage } from "./pages/HomePage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkspacePage } from "./pages/WorkspacePage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/conversation" element={<ConversationPage />} />
        <Route path="/workspace" element={<WorkspacePage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </AppShell>
  );
}
