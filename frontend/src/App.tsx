import { Navigate, Route, Routes } from "react-router-dom";
import { LoginPage } from "./pages/auth/LoginPage";
import { SignupPage } from "./pages/auth/SignupPage";
import { DashboardPage } from "./pages/DashboardPage";
import { CapturePage } from "./pages/CapturePage";
import { OcrProcessingPage } from "./pages/receipts/OcrProcessingPage";
import { OcrResultEditPage } from "./pages/receipts/OcrResultEditPage";
import { OcrExtractionReviewPage } from "./pages/receipts/OcrExtractionReviewPage";
import { AnalysisResultPage } from "./pages/receipts/AnalysisResultPage";
import { PurchaseStoragePage } from "./pages/storage/PurchaseStoragePage";
import { PurchaseTransactionStoragePage } from "./pages/storage/PurchaseTransactionStoragePage";
import { SalesStoragePage } from "./pages/storage/SalesStoragePage";
import { TrashPage } from "./pages/storage/TrashPage";
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
      <Route path="/receipts/:id/review" element={<OcrExtractionReviewPage />} />
      <Route path="/receipts/:id/edit" element={<OcrResultEditPage />} />
      <Route path="/receipts/:id/analysis" element={<AnalysisResultPage />} />
      <Route path="/storage/purchase" element={<PurchaseTransactionStoragePage />} />
      <Route path="/storage/purchase-legacy" element={<PurchaseStoragePage />} />
      <Route path="/storage/sales" element={<SalesStoragePage />} />
      <Route path="/storage/trash" element={<TrashPage />} />
      <Route path="/reports" element={<ReportPage />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
