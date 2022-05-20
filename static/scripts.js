<script>
    let company = ""

    function storeVar(el) {
        company = el.value;
        console.log(company);
    }

    window.onload = function(){
        document.getElementById("symbol").innerHTML=company;
        company = ""
    }
</script>