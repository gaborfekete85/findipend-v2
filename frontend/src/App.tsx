import { SignIn, UserButton, useAuth } from "@clerk/react";
import { Route, Routes } from "react-router";
import HomePage from "./pages/HomePage";

export default function App() {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) return null;

  if (!isSignedIn) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <SignIn routing="hash" />
      </main>
    );
  }

  return (
    <>
      <header className="flex justify-end p-4">
        <UserButton />
      </header>
      <Routes>
        <Route path="/" element={<HomePage />} />
      </Routes>
    </>
  );
}
