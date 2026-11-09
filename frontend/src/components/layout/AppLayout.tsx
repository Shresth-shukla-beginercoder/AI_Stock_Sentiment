import { Outlet } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Navbar } from "./Navbar";
import { useState } from "react";
import { EntryLoader } from "./EntryLoader";

export function AppLayout() {
  // Plays on every full app load / reload (not on in-app route changes).
  const [showLoader, setShowLoader] = useState(true);

  const handleLoaderComplete = () => {
    setShowLoader(false);
  };

  if (showLoader) {
    return <EntryLoader onComplete={handleLoaderComplete} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-ink">
      <Navbar />
      <AnimatePresence mode="wait">
        <motion.main
          key="main"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="flex-1"
        >
          <Outlet />
        </motion.main>
      </AnimatePresence>
    </div>
  );
}
