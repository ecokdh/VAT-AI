import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/auth/LoginPage";
import { SignupPage } from "./pages/auth/SignupPage";
import { DashboardPage } from "./pages/DashboardPage";
import { CapturePage } from "./pages/CapturePage";
import { OcrProcessingPage } from "./pages/receipts/OcrProcessingPage";
import { OcrResultEditPage } from "./pages/receipts/OcrResultEditPage";
import { AnalysisResultPage } from "./pages/receipts/AnalysisResultPage";
import { PurchaseStoragePage } from "./pages/storage/PurchaseStoragePage";
import { SalesStoragePage } from "./pages/storage/SalesStoragePage";
import { ReportPage } from "./pages/reports/ReportPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/capture" element={<CapturePage />} />
      <Route path="/receipts/:id/processing" element={<OcrProcessingPage />} />
      <Route path="/receipts/:id/edit" element={<OcrResultEditPage />} />
      <Route path="/receipts/:id/analysis" element={<AnalysisResultPage />} />
      <Route path="/storage/purchase" element={<PurchaseStoragePage />} />
      <Route path="/storage/sales" element={<SalesStoragePage />} />
      <Route path="/reports" element={<ReportPage />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
