import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import GpsPage from "@/pages/GpsPage";

function App() {
  return (
    <div className="App h-full">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<GpsPage />} />
        </Routes>
      </BrowserRouter>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#0a0a0a",
            border: "1px solid #1f1f1f",
            color: "#f4f4f5",
            fontFamily: "Manrope, sans-serif",
          },
        }}
      />
    </div>
  );
}

export default App;
