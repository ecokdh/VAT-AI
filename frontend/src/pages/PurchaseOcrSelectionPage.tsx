import { Link, useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { purchaseOcrOptions, purchaseOcrSelectionRoutes } from "../hooks/purchaseOcrRoute";
import "../styles/capture.css";

export function PurchaseOcrSelectionPage() {
  const [params] = useSearchParams();
  return <div className="page qa-page">
    <PageHeader title="매입 OCR" />
    <main className="page__body">
      <h1 className="screen-title">영수증 특징 선택</h1>
      <div className="purchase-ocr-options">
        {purchaseOcrSelectionRoutes.map((route) => {
          const option = purchaseOcrOptions[route];
          const captureParams = new URLSearchParams({ ocr: route });
          if (params.get("source") === "file") captureParams.set("source", "file");
          return <Link key={route} to={{ pathname: "/capture", search: captureParams.toString() }}>
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </Link>;
        })}
      </div>
    </main>
  </div>;
}
