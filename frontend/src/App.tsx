import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./layouts/AppLayout";
import { ConnectionBoard } from "./pages/ConnectionBoard";
import { SystemStatus } from "./pages/SystemStatus";
import { Assets } from "./pages/Assets";
import { StockInspector } from "./pages/StockInspector";
import { Jobs } from "./pages/Jobs";
import { ModelPerformance } from "./pages/ModelPerformance";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<ConnectionBoard />} />
        <Route path="/system" element={<SystemStatus />} />
        <Route path="/assets" element={<Assets />} />
        <Route path="/inspector" element={<StockInspector />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/models" element={<ModelPerformance />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
