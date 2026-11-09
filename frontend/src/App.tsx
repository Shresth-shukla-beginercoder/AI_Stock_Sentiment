import { Routes, Route, Navigate } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import { Dashboard } from "./pages/Dashboard";
import { Stocks } from "./pages/Stocks";
import { NewsSentiment } from "./pages/NewsSentiment";
import { AIInsights } from "./pages/AIInsights";
import { SystemStatus } from "./pages/SystemStatus";
import { Jobs } from "./pages/Jobs";
import { ModelPerformance } from "./pages/ModelPerformance";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/stocks" element={<Stocks />} />
        <Route path="/news" element={<NewsSentiment />} />
        <Route path="/insights" element={<AIInsights />} />
        <Route path="/system" element={<SystemStatus />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/models" element={<ModelPerformance />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
