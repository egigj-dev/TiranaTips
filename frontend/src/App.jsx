import { useState } from 'react'
import './App.css'
import { Routes, Route } from "react-router-dom";
import Home from "./components/Home/Home";
import Navigation from "./components/Navigation/Navigation";
import Footer from "./components/Footer/Footer";
import Ask from "./components/Ask/Ask";
import ForYou from "./components/ForYou/ForYou";
import Explore from "./components/Explore/Explore";


function App() {
  return (
    <>
      <Navigation />

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/foryou" element={<ForYou />} />
        <Route path="/explore" element={<Explore />} />

      </Routes>

      <Footer/>
    </>
  );
}

export default App;