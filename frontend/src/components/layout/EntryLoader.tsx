import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

interface EntryLoaderProps {
  onComplete: () => void;
}

export function EntryLoader({ onComplete }: EntryLoaderProps) {
  const [progress, setProgress] = useState(0);
  const [isExiting, setIsExiting] = useState(false);
  const [currentPhase, setCurrentPhase] = useState(0);
  const reducedMotion = useReducedMotion();

  const phases = [
    { label: "INITIALIZING NEURAL NETWORK", sublabel: "Connecting to market feeds" },
    { label: "ANALYZING SENTIMENT DATA", sublabel: "Processing 10,000+ signals" },
    { label: "CALIBRATING PREDICTIONS", sublabel: "Running ML models" },
    { label: "LAUNCHING TERMINAL", sublabel: "Ready for deployment" },
  ];

  useEffect(() => {
    const startTime = Date.now();
    // Motion-sensitive users get a fast, quiet pass instead of the full 3.2s sequence.
    const duration = reducedMotion ? 500 : 3200;

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const newProgress = Math.min((elapsed / duration) * 100, 100);
      setProgress(newProgress);

      // Update phase based on progress
      if (newProgress < 25) setCurrentPhase(0);
      else if (newProgress < 50) setCurrentPhase(1);
      else if (newProgress < 75) setCurrentPhase(2);
      else setCurrentPhase(3);

      if (newProgress >= 100) {
        clearInterval(interval);
        const exitDelay = reducedMotion ? 0 : 400;
        const fadeMs = reducedMotion ? 100 : 800;
        setTimeout(() => {
          setIsExiting(true);
          setTimeout(onComplete, fadeMs);
        }, exitDelay);
      }
    }, 30);

    return () => clearInterval(interval);
  }, [onComplete, reducedMotion]);

  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: isExiting ? 0 : 1 }}
      transition={{ duration: 0.8, ease: "easeInOut" }}
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-gradient-to-br from-ink via-navy to-ink overflow-hidden"
    >
      {/* Animated grid background */}
      <motion.div
        className="absolute inset-0 opacity-[0.03]"
        animate={{
          backgroundPosition: ["0% 0%", "100% 100%"],
        }}
        transition={{
          duration: 20,
          repeat: Infinity,
          ease: "linear",
        }}
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(59, 130, 246, 0.1) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(59, 130, 246, 0.1) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      />

      {/* Gradient orbs */}
      <motion.div
        className="absolute top-1/4 left-1/4 w-96 h-96 rounded-full blur-3xl"
        animate={{
          scale: [1, 1.2, 1],
          opacity: [0.1, 0.2, 0.1],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        style={{
          background: "radial-gradient(circle, rgba(59, 130, 246, 0.3) 0%, transparent 70%)",
        }}
      />
      <motion.div
        className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full blur-3xl"
        animate={{
          scale: [1.2, 1, 1.2],
          opacity: [0.15, 0.25, 0.15],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 1,
        }}
        style={{
          background: "radial-gradient(circle, rgba(245, 158, 11, 0.2) 0%, transparent 70%)",
        }}
      />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center gap-12 px-4">
        {/* Logo reveal */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.6, ease: [0.34, 1.56, 0.64, 1] }}
          className="text-center"
        >
          <motion.h1
            className="font-display text-7xl font-bold tracking-tight bg-gradient-to-r from-glow-blue via-bell-amber to-glow-blue bg-clip-text text-transparent"
            animate={{
              backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"],
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: "linear",
            }}
            style={{
              backgroundSize: "200% 100%",
            }}
          >
            NEXTBELL
          </motion.h1>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ delay: 0.5, duration: 0.8 }}
            className="h-[1px] bg-gradient-to-r from-transparent via-glow-blue to-transparent mx-auto mt-4"
          />
          <motion.p
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.8, duration: 0.6 }}
            className="mt-4 font-mono text-sm tracking-[0.2em] text-muted uppercase"
          >
            Launch control for tomorrow's market
          </motion.p>
        </motion.div>

        {/* Enhanced orbital loader */}
        <div className="relative h-48 w-48">
          {/* Multiple rotating rings */}
          {[0, 1, 2].map((index) => (
            <motion.div
              key={index}
              className="absolute inset-0"
              animate={{ rotate: 360 }}
              transition={{
                duration: 3 + index * 0.5,
                repeat: Infinity,
                ease: "linear",
              }}
            >
              <svg
                width="192"
                height="192"
                viewBox="0 0 192 192"
                fill="none"
                className="absolute inset-0"
              >
                <circle
                  cx="96"
                  cy="96"
                  r={80 - index * 15}
                  stroke={index === 0 ? "#3b82f6" : index === 1 ? "#f59e0b" : "#3b82f6"}
                  strokeWidth="1"
                  strokeDasharray={index === 1 ? "10 10" : index === 2 ? "5 15" : ""}
                  opacity={0.3 - index * 0.05}
                  strokeLinecap="round"
                />
              </svg>
            </motion.div>
          ))}

          {/* Center icon with pulse */}
          <motion.div
            className="absolute inset-0 flex items-center justify-center"
            animate={{
              scale: [1, 1.05, 1],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          >
            <div className="relative">
              <motion.div
                className="absolute inset-0 rounded-full bg-glow-blue blur-xl"
                animate={{
                  opacity: [0.3, 0.6, 0.3],
                  scale: [1, 1.2, 1],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
              />
              <img
                src="/favicon.png"
                alt="NEXTBELL"
                className="relative h-16 w-16 rounded-lg"
              />
            </div>
          </motion.div>

          {/* Orbiting particles */}
          {[0, 120, 240].map((angle, idx) => (
            <motion.div
              key={idx}
              className="absolute top-1/2 left-1/2 w-2 h-2"
              animate={{
                rotate: [angle, angle + 360],
              }}
              transition={{
                duration: 3,
                repeat: Infinity,
                ease: "linear",
              }}
              style={{
                transformOrigin: "0 0",
              }}
            >
              <motion.div
                className="w-2 h-2 rounded-full"
                style={{
                  background: idx === 0 ? "#3b82f6" : idx === 1 ? "#f59e0b" : "#10b981",
                  boxShadow: `0 0 10px ${idx === 0 ? "#3b82f6" : idx === 1 ? "#f59e0b" : "#10b981"}`,
                }}
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.6, 1, 0.6],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: idx * 0.2,
                }}
              />
            </motion.div>
          ))}
        </div>

        {/* Progress section */}
        <div className="w-full max-w-md space-y-6">
          {/* Phase indicator */}
          <AnimatePresence mode="wait">
            <motion.div
              key={currentPhase}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.4 }}
              className="text-center space-y-2"
            >
              <p className="font-mono text-lg font-semibold tracking-wide text-glow-blue">
                {phases[currentPhase].label}
              </p>
              <p className="font-mono text-xs tracking-widest text-muted uppercase">
                {phases[currentPhase].sublabel}
              </p>
            </motion.div>
          </AnimatePresence>

          {/* Enhanced progress bar */}
          <div className="relative">
            {/* Background track */}
            <div className="h-1 bg-navy/50 rounded-full overflow-hidden backdrop-blur-sm border border-white/5">
              {/* Progress fill with gradient */}
              <motion.div
                className="h-full bg-gradient-to-r from-glow-blue via-bell-amber to-glow-blue rounded-full relative"
                style={{
                  width: `${progress}%`,
                  backgroundSize: "200% 100%",
                }}
                animate={{
                  backgroundPosition: ["0% 50%", "100% 50%", "0% 50%"],
                }}
                transition={{
                  duration: 2,
                  repeat: Infinity,
                  ease: "linear",
                }}
              >
                {/* Glow effect */}
                <motion.div
                  className="absolute inset-0 rounded-full"
                  style={{
                    boxShadow: "0 0 20px rgba(59, 130, 246, 0.6)",
                  }}
                  animate={{
                    opacity: [0.6, 1, 0.6],
                  }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    ease: "easeInOut",
                  }}
                />
              </motion.div>
            </div>

            {/* Percentage display */}
            <motion.div
              className="absolute -top-8 left-0 font-mono text-2xl font-bold text-glow-blue tabular-nums"
              style={{
                left: `${Math.min(progress, 95)}%`,
                transform: "translateX(-50%)",
              }}
              animate={{
                scale: [1, 1.05, 1],
              }}
              transition={{
                duration: 0.5,
                repeat: Infinity,
              }}
            >
              {Math.floor(progress)}
              <span className="text-sm text-muted ml-0.5">%</span>
            </motion.div>
          </div>

          {/* Loading dots */}
          <div className="flex justify-center gap-2">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-glow-blue"
                animate={{
                  scale: [1, 1.5, 1],
                  opacity: [0.3, 1, 0.3],
                }}
                transition={{
                  duration: 1.5,
                  repeat: Infinity,
                  delay: i * 0.2,
                }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Corner decorations */}
      <div className="absolute top-4 left-4 font-mono text-[10px] text-muted/40 tracking-wider">
        NEXTBELL v1.0.0
      </div>
      <div className="absolute top-4 right-4 font-mono text-[10px] text-muted/40 tracking-wider">
        {new Date().toISOString().split('T')[0]}
      </div>
      <div className="absolute bottom-4 left-4 font-mono text-[10px] text-muted/40 tracking-wider">
        SECURE CONNECTION
      </div>
      <div className="absolute bottom-4 right-4 font-mono text-[10px] text-muted/40 tracking-wider flex items-center gap-1">
        <motion.div
          className="w-1.5 h-1.5 rounded-full bg-success"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        LIVE
      </div>
    </motion.div>
  );
}
