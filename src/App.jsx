import React, { useState } from 'react';
import { firebaseConfig } from './firebaseConfig';
import { initializeApp } from 'firebase/app';
import { getFirestore, doc, setDoc, deleteDoc } from 'firebase/firestore';

// Initialize Firebase
const app = initializeApp({
    apiKey: import.meta.env.VITE_API_KEY,
    authDomain: import.meta.env.VITE_AUTH_DOMAIN,
    projectId: import.meta.env.VITE_PROJECT_ID,
    storageBucket: import.meta.env.VITE_STORAGE_BUCKET,
    messagingSenderId: import.meta.env.VITE_MESSAGING_SENDER_ID,
    appId: import.meta.env.VITE_APP_ID
});
const db = getFirestore(app);

const App = () => {
    const [exercises, setExercises] = useState([]);

    const handleAddExercise = async (exercise) => {
        try {
            const docRef = doc(db, 'exercises', exercise.id);
            await setDoc(docRef, exercise);
            setExercises((prev) => [...prev, exercise]);
        } catch (error) {
            console.error('Error adding exercise:', error);
        }
    };

    const handleDeleteExercise = async (id) => {
        try {
            await deleteDoc(doc(db, 'exercises', id));
            setExercises((prev) => prev.filter(exercise => exercise.id !== id));
        } catch (error) {
            console.error('Error deleting exercise:', error);
        }
    };

    return (
        <div>
            {/* Render exercises and controls here */}
        </div>
    );
};

export default App;