standingsApp.controller('PilotListController', function ($scope, $http) {
    $scope.getData = function () {
        $http.get(urls.pilots_json).then(function(response) {
            // Success
            document.getElementById("div_spinner").style.display = 'none';
            document.getElementById("div_results").style.visibility = 'visible';
            $scope.pilots = response.data;
        }, function(response) {
            // Unsuccessful
        });
    };

    $scope.currentPage = 1;
    $scope.pageSize = '50';
    $scope.getData();
});
