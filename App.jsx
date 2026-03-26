import React, { useState, useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, onAuthStateChanged } from 'firebase/auth';
import { getFirestore, collection, doc, addDoc, onSnapshot, deleteDoc } from 'firebase/firestore';
import { ChevronRight, AlertCircle, Activity, ShieldCheck, Award } from 'lucide-react';
const firebaseConfig = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
    authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_FIREBASE_APP_ID
};
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
const appId = "chudleigh-health-portal";
const App = () => {
    const [currentPage, setCurrentPage] = useState('home');
    const [showSafetyAlert, setShowSafetyAlert] = useState(false);
    const [user, setUser] = useState(null);
    const [exercises, setExercises] = useState([]);
    const [isPractitioner, setIsPractitioner] = useState(false);
    const [newExercise, setNewExercise] = useState({ name: '', videoUrl: '', stage: 1 });
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    useEffect(() => {
        const initAuth = async () => {
            try {
                await signInAnonymously(auth);
            } catch (err) {
                console.error('Auth error:', err);
                setError('Failed to initialize authentication');
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
            setExercises(snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() })));
        }, (err) => {
            console.error('Error fetching exercises:', err);
            setError('Failed to load exercises');
        });
        return () => unsubscribe();
    }, [user]);
    const navigateTo = (page) => {
        setCurrentPage(page);
        window.scrollTo(0, 0);
    };
    const handleAddExercise = async (e) => {
        e.preventDefault();
        if (!newExercise.name || !newExercise.videoUrl) {
            setError('Please fill in all fields');
            return;
        }
        try {
            setIsLoading(true);
            setError(null);
            const exercisesRef = collection(db, 'artifacts', appId, 'public', 'data', 'exercises');
            await addDoc(exercisesRef, { ...newExercise, createdAt: new Date().toISOString() });
            setNewExercise({ name: '', videoUrl: '', stage: newExercise.stage });
        } catch (err) {
            console.error('Error adding exercise:', err);
            setError('Failed to save exercise');
        } finally {
            setIsLoading(false);
        }
    };
    const handleDeleteExercise = async (id) => {
        try {
            setIsLoading(true);
            setError(null);
            const docRef = doc(db, 'artifacts', appId, 'public', 'data', 'exercises', id);
            await deleteDoc(docRef);
        } catch (err) {
            console.error('Error deleting exercise:', err);
            setError('Failed to delete exercise');
        } finally {
            setIsLoading(false);
        }
    };
    const getYoutubeId = (url) => {
        const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/;
        const match = url.match(regExp);
        return (match && match[2].length === 11) ? match[2] : null;
    };
    const Header = () => (
        <header className="bg-slate-900 text-white p-4 sticky top-0 z-50">
            <div className="max-w-4xl mx-auto flex justify-between items-center">
                <div className="flex items-center space-x-2 cursor-pointer" onClick={() => navigateTo('home')}>
                    <Activity className="w-6 h-6 text-blue-500" />
                    <h1 className="text-xl font-bold tracking-tight">CHUDLEIGH HEALTH</h1>
                </div>
                <button onClick={() => setIsPractitioner(!isPractitioner)} className="px-3 py-1 bg-slate-800 rounded-full text-[10px]">
                    {isPractitioner ? 'EXIT ADMIN' : 'PRACTITIONER LOGIN'}
                </button>
            </div>
        </header>
    );
    const VideoEmbed = ({ url }) => {
        const videoId = getYoutubeId(url);
        if (!videoId) return <div className="p-4 bg-slate-100 rounded text-xs">No video.</div>;
        return <div className="aspect-video w-full mt-3 rounded-xl overflow-hidden bg-black"><iframe className="w-full h-full" src={`https://www.youtube.com/embed/${videoId}`} frameBorder="0" allowFullScreen></iframe></div>;
    };
    const HomePage = () => (
        <div className="p-6 text-center max-w-sm mx-auto">
            <h2 className="text-3xl font-black mb-10 uppercase">Recovery Portal</h2>
            <div className="space-y-4">
                {[1, 2, 3].map(s => (
                    <div key={s} onClick={() => navigateTo(`stage${s}`)} className="p-5 rounded-3xl border-2 bg-white flex items-center justify-between cursor-pointer hover:border-blue-500">
                        <div className="flex items-center">
                            <div className="w-12 h-12 bg-slate-50 rounded-xl flex items-center justify-center mr-4">{s===1?<ShieldCheck/>:s===2?<Activity/>:<Award/>}</div>
                            <div className="text-left"><h3 className="font-black">STAGE {s}</h3><p className="text-[10px] uppercase text-slate-400">{s===1?'Symptomatic':s===2?'Rehab':'Life'}</p></div>
                        </div>
                        <ChevronRight className="w-5 h-5 text-slate-300" />
                    </div>
                ))}
            </div>
        </div>
    );
    const StagePage = ({ num, title }) => {
        const stageEx = exercises.filter(ex => ex.stage === num);
        return (
            <div className="p-6 max-w-2xl mx-auto">
                <button onClick={() => navigateTo('home')} className="text-[10px] font-black mb-6">BACK</button>
                <h2 className="text-2xl font-black mb-2 uppercase">Stage {num}: {title}</h2>
                <div className="bg-red-50 p-4 rounded-xl mb-8"><p className="text-red-800 text-xs font-bold italic">STOP if you feel pain.</p></div>
                <div className="space-y-8">
                    {stageEx.map(ex => (
                        <div key={ex.id} className="bg-white p-6 rounded-3xl border shadow-sm"><h4 className="font-black mb-4 uppercase">{ex.name}</h4><VideoEmbed url={ex.videoUrl} /></div>
                    ))}
                </div>
            </div>
        );
    };
    const PractitionerPortal = () => (
        <div className="p-6 max-w-2xl mx-auto">
            <h2 className="text-xl font-black mb-8 uppercase text-slate-800">Admin</h2>
            {error && <div className="bg-red-100 p-4 rounded-xl mb-4 text-red-800 text-sm">{error}</div>}
            <form onSubmit={handleAddExercise} className="space-y-4 bg-white p-8 rounded-[30px] border shadow-xl mb-10">
                <input type="text" placeholder="Title" className="w-full p-4 bg-slate-50 border rounded-xl" value={newExercise.name} onChange={(e) => setNewExercise({...newExercise, name: e.target.value})} disabled={isLoading} />
                <input type="text" placeholder="YouTube Link" className="w-full p-4 bg-slate-50 border rounded-xl" value={newExercise.videoUrl} onChange={(e) => setNewExercise({...newExercise, videoUrl: e.target.value})} disabled={isLoading} />
                <div className="flex gap-2">
                    {[1, 2, 3].map(s => (
                        <button key={s} type="button" onClick={() => setNewExercise({...newExercise, stage: s})} className={`flex-1 py-4 rounded-xl font-black border ${newExercise.stage === s ? 'bg-blue-600 text-white' : 'bg-white'}`} disabled={isLoading}>S{s}</button>
                    ))}
                </div>
                <button type="submit" className="w-full bg-slate-900 text-white py-4 rounded-xl font-black disabled:opacity-50" disabled={isLoading}>{isLoading ? 'SAVING...' : 'SAVE TO CLOUD'}</button>
            </form>
        </div>
    );
    return (
        <div className="min-h-screen bg-slate-50 pb-24 font-sans text-left">
            <Header />
            {error && !isPractitioner && <div className="bg-red-100 p-4 m-4 rounded-xl text-red-800 text-sm">{error}</div>}  
            {isPractitioner ? <PractitionerPortal /> : ( 
                <> 
                    {currentPage === 'home' && <HomePage />}
                    {currentPage === 'stage1' && <StagePage num={1} title="Symptomatic" />}  
                    {currentPage === 'stage2' && <StagePage num={2} title="Rehab" />}  
                    {currentPage === 'stage3' && <StagePage num={3} title="Maintenance" />}  
                </>
            )}
            <button onClick={() => setShowSafetyAlert(true)} className="fixed bottom-24 right-6 bg-red-600 text-white p-4 rounded-3xl shadow-2xl z-50 animate-bounce"><AlertCircle/></button>
            {showSafetyAlert && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/70 backdrop-blur-sm">
                    <div className="bg-white rounded-[40px] p-10 max-w-sm w-full text-center shadow-2xl">
                        <h2 className="text-xl font-black mb-4 uppercase">STOP & CONTACT US</h2>
                        <p className="text-slate-500 mb-8 italic text-sm">Pain is a signal. Stop and call the clinic.</p>
                        <button onClick={() => setShowSafetyAlert(false)} className="w-full bg-slate-900 text-white py-4 rounded-2xl font-black uppercase tracking-widest text-[10px]">I UNDERSTAND</button>
                    </div>
                </div>
            )}
        </div>
    );
};
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);