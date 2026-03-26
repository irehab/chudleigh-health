import React, { useState, useEffect } from 'react';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, signInWithCustomToken, onAuthStateChanged } from 'firebase/auth';
import { getFirestore, collection, doc, addDoc, onSnapshot, deleteDoc, query } from 'firebase/firestore';
import { 
  ChevronRight, 
  ChevronLeft, 
  AlertCircle, 
  Activity, 
  ShieldCheck, 
  Award, 
  Calendar, 
  BookOpen, 
  Heart, 
  Info,
  CheckCircle2,
  Clock,
  ArrowRight,
  User,
  Plus,
  Trash2,
  Lock,
  PlayCircle,
  X
} from 'lucide-react';

// --- Firebase Configuration ---
// IMPORTANT: When deploying to your own site (Vercel/GitHub), replace this block 
// with your actual Firebase config object from the Firebase Console.
// Example: const firebaseConfig = { apiKey: "YOUR_API_KEY", ... };
const firebaseConfig = typeof __firebase_config !== 'undefined' ? JSON.parse(__firebase_config) : {
  apiKey: "",
  authDomain: "",
  projectId: "",
  storageBucket: "",
  messagingSenderId: "",
  appId: ""
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const appId = typeof __app_id !== 'undefined' ? __app_id : 'atrium-recovery-default';

const App = () => {
  const [currentPage, setCurrentPage] = useState('home');
  const [userStage, setUserStage] = useState(1);
  const [showSafetyAlert, setShowSafetyAlert] = useState(false);
  const [completedExercises, setCompletedExercises] = useState({});
  const [user, setUser] = useState(null);
  const [exercises, setExercises] = useState([]);
  const [isPractitioner, setIsPractitioner] = useState(false);
  
  const [newExercise, setNewExercise] = useState({ name: '', videoUrl: '', stage: 1 });

  useEffect(() => {
    const initAuth = async () => {
      if (typeof __initial_auth_token !== 'undefined' && __initial_auth_token) {
        await signInWithCustomToken(auth, __initial_auth_token);
      } else {
        await signInAnonymously(auth);
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  useEffect(() => {
    if (!user) return;
    const exercisesRef = collection(db, 'artifacts', appId, 'public', 'data', 'exercises');
    const unsubscribe = onSnapshot(exercisesRef, (snapshot) => {
      const exerciseList = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }));
      setExercises(exerciseList);
    }, (error) => {});
    return () => unsubscribe();
  }, [user]);

  const navigateTo = (page) => {
    setCurrentPage(page);
    window.scrollTo(0, 0);
  };

  const handleAddExercise = async (e) => {
    e.preventDefault();
    if (!newExercise.name || !newExercise.videoUrl) return;
    try {
      const exercisesRef = collection(db, 'artifacts', appId, 'public', 'data', 'exercises');
      await addDoc(exercisesRef, {
        ...newExercise,
        createdAt: new Date().toISOString()
      });
      setNewExercise({ name: '', videoUrl: '', stage: newExercise.stage });
    } catch (err) { console.error(err); }
  };

  const handleDeleteExercise = async (id) => {
    try {
      const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'exercises', id);
      await deleteDoc(docRef);
    } catch (err) { console.error(err); }
  };

  const getYoutubeId = (url) => {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
  };

  const SafetyNotice = () => (
    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-6 rounded-r-lg">
      <div className="flex items-start">
        <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 mr-3" />
        <div>
          <h3 className="text-red-800 font-bold uppercase text-xs mb-1">Critical Safety Rule</h3>
          <p className="text-red-700 text-sm italic">
            "Follow advice given and always listen to your body. If any of the exercises cause you pain - <strong>STOP</strong> and contact us before you resume your plan."
          </p>
        </div>
      </div>
    </div>
  );

  const Header = () => (
    <header className="bg-slate-900 text-white p-4 sticky top-0 z-50">
      <div className="max-w-4xl mx-auto flex justify-between items-center">
        <div className="flex items-center space-x-2 cursor-pointer" onClick={() => navigateTo('home')}>
          <Activity className="w-6 h-6 text-blue-500" />
          <h1 className="text-xl font-bold tracking-tight">THE ATRIUM</h1>
        </div>
        <button 
          onClick={() => setIsPractitioner(!isPractitioner)}
          className={`px-3 py-1.5 rounded-full text-[10px] font-bold transition-all ${isPractitioner ? 'bg-amber-500 text-white shadow-lg' : 'bg-slate-700 text-slate-300'}`}
        >
          {isPractitioner ? 'EXIT ADMIN' : 'PRACTITIONER LOGIN'}
        </button>
      </div>
    </header>
  );

  const VideoEmbed = ({ url }) => {
    const videoId = getYoutubeId(url);
    if (!videoId) return <div className="p-4 bg-slate-100 rounded text-xs">No valid YouTube link.</div>;
    return (
      <div className="aspect-video w-full mt-3 rounded-lg overflow-hidden bg-black">
        <iframe className="w-full h-full" src={`https://www.youtube.com/embed/${videoId}`} title="Video" frameBorder="0" allowFullScreen></iframe>
      </div>
    );
  };

  const PractitionerPortal = () => (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-black mb-8 text-slate-800">Practitioner Portal</h2>
      <form onSubmit={handleAddExercise} className="space-y-4 bg-white p-6 rounded-3xl border border-slate-200 shadow-sm mb-8">
        <input type="text" placeholder="Exercise Title" className="w-full p-3 bg-slate-50 border rounded-xl text-sm" value={newExercise.name} onChange={(e) => setNewExercise({...newExercise, name: e.target.value})} />
        <input type="text" placeholder="YouTube URL" className="w-full p-3 bg-slate-50 border rounded-xl text-sm" value={newExercise.videoUrl} onChange={(e) => setNewExercise({...newExercise, videoUrl: e.target.value})} />
        <div className="flex gap-2">
          {[1, 2, 3].map(s => (
            <button key={s} type="button" onClick={() => setNewExercise({...newExercise, stage: s})} className={`flex-1 py-3 rounded-xl text-xs font-bold border transition-all ${newExercise.stage === s ? 'bg-blue-600 text-white' : 'bg-white text-slate-400'}`}>STAGE {s}</button>
          ))}
        </div>
        <button type="submit" className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold hover:bg-black transition-colors">SAVE TO CLOUD</button>
      </form>
      <div className="space-y-4">
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest px-2">Current Exercises</h3>
        {exercises.map(ex => (
          <div key={ex.id} className="bg-white p-4 rounded-2xl border flex items-center justify-between shadow-sm">
            <div className="flex items-center gap-3">
              <span className={`px-2 py-1 rounded text-[10px] font-bold ${ex.stage === 1 ? 'bg-blue-100 text-blue-600' : ex.stage === 2 ? 'bg-green-100 text-green-600' : 'bg-amber-100 text-amber-600'}`}>S{ex.stage}</span>
              <p className="text-sm font-bold text-slate-700">{ex.name}</p>
            </div>
            <button onClick={() => handleDeleteExercise(ex.id)} className="text-slate-300 hover:text-red-500 transition-colors"><Trash2 className="w-5 h-5" /></button>
          </div>
        ))}
        {exercises.length === 0 && <p className="text-center text-slate-400 italic text-sm py-4">No exercises added yet.</p>}
      </div>
    </div>
  );

  const HomePage = () => (
    <div className="p-6 text-center max-w-sm mx-auto">
      <h2 className="text-3xl font-extrabold text-slate-800 mb-2">3 Stages to Recovery</h2>
      <p className="text-slate-500 mb-10 text-sm">"Not just getting by, always getting better."</p>
      <div className="space-y-4">
        {[1, 2, 3].map(s => (
          <div key={s} onClick={() => navigateTo(`stage${s}`)} className="p-5 rounded-2xl border-2 border-slate-100 bg-white shadow-sm flex items-center justify-between cursor-pointer hover:border-blue-500 transition-all group">
            <div className="flex items-center">
              <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center mr-4 group-hover:bg-blue-50 transition-colors">
                {s === 1 ? <ShieldCheck className="w-6 h-6 text-blue-600" /> : s === 2 ? <Activity className="w-6 h-6 text-green-600" /> : <Award className="w-6 h-6 text-amber-600" />}
              </div>
              <div className="text-left">
                <h3 className="font-bold text-slate-800">Stage {s}</h3>
                <p className="text-[10px] text-slate-400 uppercase font-black">{s===1?'Symptomatic':s===2?'Rehabilitation':'Maintenance'}</p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-slate-300 group-hover:text-blue-500" />
          </div>
        ))}
      </div>
    </div>
  );

  const StagePage = ({ num, title, color }) => {
    const stageEx = exercises.filter(ex => ex.stage === num);
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <button onClick={() => navigateTo('home')} className="flex items-center text-slate-500 text-sm mb-6 hover:text-slate-800 transition-colors"><ChevronLeft className="w-4 h-4 mr-1" /> Back to Journey</button>
        <h2 className="text-2xl font-black mb-6 text-slate-800">Stage {num}: {title}</h2>
        <SafetyNotice />
        <div className="space-y-8 mt-8">
          {stageEx.map(ex => (
            <div key={ex.id} className="bg-white p-6 rounded-3xl border border-slate-100 shadow-sm">
              <h4 className="font-bold text-slate-800 mb-4 text-lg">{ex.name}</h4>
              <VideoEmbed url={ex.videoUrl} />
            </div>
          ))}
          {stageEx.length === 0 && (
            <div className="text-center py-16 border-2 border-dashed border-slate-200 rounded-3xl">
              <Activity className="w-12 h-12 text-slate-200 mx-auto mb-4" />
              <p className="text-slate-400 italic text-sm">Your specific plan for this stage is being finalized.</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 font-sans">
      <Header />
      <div className="max-w-4xl mx-auto pb-24">
        {isPractitioner ? <PractitionerPortal /> : (
          <>
            {currentPage === 'home' && <HomePage />}
            {currentPage === 'stage1' && <StagePage num={1} title="Symptomatic Phase" color="blue" />}
            {currentPage === 'stage2' && <StagePage num={2} title="Rehabilitation Phase" color="green" />}
            {currentPage === 'stage3' && <StagePage num={3} title="Maintenance Phase" color="amber" />}
          </>
        )}
      </div>
      
      {!isPractitioner && (
        <nav className="fixed bottom-0 left-0 right-0 bg-white/80 backdrop-blur-md border-t border-slate-200 p-2 flex justify-around items-center z-40">
          <button onClick={() => navigateTo('home')} className={`flex flex-col items-center p-2 rounded-xl transition-all ${currentPage === 'home' ? 'text-blue-600' : 'text-slate-400'}`}>
            <ShieldCheck className="w-6 h-6" />
            <span className="text-[10px] font-bold uppercase mt-1">Journey</span>
          </button>
          <button className="flex flex-col items-center p-2 text-slate-400 opacity-50 cursor-not-allowed">
            <BookOpen className="w-6 h-6" />
            <span className="text-[10px] font-bold uppercase mt-1">Vault</span>
          </button>
          <button className="flex flex-col items-center p-2 text-slate-400 opacity-50 cursor-not-allowed">
            <Calendar className="w-6 h-6" />
            <span className="text-[10px] font-bold uppercase mt-1">Book</span>
          </button>
        </nav>
      )}

      <SafetyModal show={showSafetyAlert} onClose={() => setShowSafetyAlert(false)} />
    </div>
  );
};

const SafetyModal = ({ show, onClose }) => {
  if (!show) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-sm">
      <div className="bg-white rounded-3xl p-8 max-w-sm w-full text-center shadow-2xl animate-in zoom-in duration-300">
        <AlertCircle className="w-16 h-16 text-red-600 mx-auto mb-4" />
        <h2 className="text-2xl font-black mb-4 uppercase text-slate-800">Stop & Contact Us</h2>
        <p className="text-slate-600 mb-8 italic text-sm leading-relaxed">
          "If any of the exercises cause you pain - <strong>STOP</strong> and contact us before you resume your plan."
        </p>
        <button onClick={onClose} className="w-full bg-slate-900 text-white py-4 rounded-xl font-bold hover:bg-black transition-colors">I UNDERSTAND</button>
      </div>
    </div>
  );
};

export default App;
