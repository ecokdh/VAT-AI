import {useEffect,useState} from 'react';
import {NavLink} from 'react-router-dom';
import {apiClient} from '../api/client';
export function TeamBenchmarkTab(){const [allowed,setAllowed]=useState(false);useEffect(()=>{apiClient.get('/v2/team-benchmark/access').then(r=>setAllowed(r.data.allowed)).catch(()=>setAllowed(false));},[]);return allowed?<NavLink to="/storage/team">팀 테스트 자료</NavLink>:null;}
