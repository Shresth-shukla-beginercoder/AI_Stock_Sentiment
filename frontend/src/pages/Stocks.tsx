import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { PageContainer } from "../components/layout";
import { StockList, StockDetail } from "../components/stocks";
import { TickerReport } from "../components/reports";
import { Button } from "../components/common/Button";
import { ArrowLeft } from "lucide-react";

export function Stocks() {
  const [searchParams] = useSearchParams();
  const initialTicker = searchParams.get("ticker");
  const [selectedTicker, setSelectedTicker] = useState<string | null>(initialTicker);

  const handleSelect = (ticker: string) => {
    setSelectedTicker(ticker);
    // Update URL
    const url = new URL(window.location.href);
    url.searchParams.set("ticker", ticker);
    window.history.pushState({}, "", url);
  };

  const handleBack = () => {
    setSelectedTicker(null);
    // Clear URL
    const url = new URL(window.location.href);
    url.searchParams.delete("ticker");
    window.history.pushState({}, "", url);
  };

  return (
    <PageContainer
      title="Stocks"
      subtitle="Track and analyze stocks with sentiment and predictions"
      action={
        selectedTicker ? (
          <Button variant="ghost" size="sm" onClick={handleBack}>
            <ArrowLeft className="mr-1.5 h-4 w-4" />
            Back to list
          </Button>
        ) : undefined
      }
    >
      <AnimatePresence mode="wait">
        {selectedTicker ? (
          <motion.div
            key={selectedTicker}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.2 }}
          >
            <StockDetail ticker={selectedTicker} />
          </motion.div>
        ) : (
          <motion.div
            key="list"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            transition={{ duration: 0.2 }}
          >
            <TickerReport />
            <StockList onSelect={handleSelect} />
          </motion.div>
        )}
      </AnimatePresence>
    </PageContainer>
  );
}