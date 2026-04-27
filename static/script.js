const tabs=document.querySelectorAll('.nav');
const title=document.getElementById('title');
const names={dashboard:'Dashboard',salarios:'Salários',contas:'Contas & Boletos',scanner:'Escanear Boleto',relatorios:'Relatórios',acessos:'Acessos'};
function showTab(t){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.nav').forEach(x=>x.classList.remove('active'));document.getElementById(t)?.classList.add('active');document.querySelector(`[data-tab="${t}"]`)?.classList.add('active');if(title)title.textContent=names[t]||'Dashboard';document.getElementById('sidebar')?.classList.remove('open');history.replaceState(null,'',`?tab=${t}`)}
tabs.forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
function toggleMenu(){document.getElementById('sidebar').classList.toggle('open')}
function openModal(id){document.getElementById(id).classList.add('open')}
function closeModal(id){document.getElementById(id).classList.remove('open')}
document.querySelectorAll('.modal').forEach(m=>m.addEventListener('click',e=>{if(e.target===m)m.classList.remove('open')}));
function novoSalario(){document.getElementById('sal_id').value='';document.getElementById('sal_nome').value='';document.getElementById('sal_cargo').value='';document.getElementById('sal_salario').value='';document.getElementById('sal_data').value='';document.getElementById('sal_status').value='Pendente';openModal('modalSalario')}
function novaConta(){document.getElementById('cont_id').value='';document.getElementById('cont_descricao').value='';document.getElementById('cont_categoria').value='Energia';document.getElementById('cont_valor').value='';document.getElementById('cont_vencimento').value='';document.getElementById('cont_status').value='Pendente';document.getElementById('cont_codigo').value='';openModal('modalConta')}
function editSalario(id,nome,cargo,salario,data,status){document.getElementById('sal_id').value=id;document.getElementById('sal_nome').value=nome;document.getElementById('sal_cargo').value=cargo;document.getElementById('sal_salario').value=salario;document.getElementById('sal_data').value=data;document.getElementById('sal_status').value=status;openModal('modalSalario')}
function editConta(id,desc,cat,valor,venc,status,codigo){document.getElementById('cont_id').value=id;document.getElementById('cont_descricao').value=desc;document.getElementById('cont_categoria').value=cat;document.getElementById('cont_valor').value=valor;document.getElementById('cont_vencimento').value=venc;document.getElementById('cont_status').value=status;document.getElementById('cont_codigo').value=codigo;openModal('modalConta')}
const tab=new URLSearchParams(location.search).get('tab');if(tab)showTab(tab);
